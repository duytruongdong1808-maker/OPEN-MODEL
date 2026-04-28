from __future__ import annotations

import asyncio
from contextlib import suppress
from importlib import import_module
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response, StreamingResponse

from ....agent import READ_ONLY_EMAIL_PROTOCOL, AgentLoop, AgentStep
from ....utils import DEFAULT_SYSTEM_PROMPT
from ...core.runtime import SupportsStreamingReply
from ...repositories.conversation_store import ConversationStore
from ...schemas import (
    AssistantDeltaPayload,
    ChatStreamRequest,
    ConversationDetail,
    ConversationSummary,
    ErrorPayload,
    MessageCompletePayload,
    MessageStartPayload,
    StepUpdatePayload,
)
from ...services.audit_service import AuditLogger
from ...services.chat_stream_service import (
    audit_agent_tool_call,
    build_steps,
    sse_event,
)
from ..deps import get_audit_logger, get_current_user_id, get_runtime, get_store
router = APIRouter()


def _app_compat():
    return import_module("src.server.app")


@router.get("/conversations", response_model=list[ConversationSummary])
async def list_conversations_endpoint(
    conversation_store: ConversationStore = Depends(get_store),
    user_id: str = Depends(get_current_user_id),
) -> list[ConversationSummary]:
    return await conversation_store.list_conversations(user_id)


@router.post("/conversations", response_model=ConversationSummary)
async def create_conversation_endpoint(
    request: Request,
    conversation_store: ConversationStore = Depends(get_store),
    user_id: str = Depends(get_current_user_id),
    audit: AuditLogger = Depends(get_audit_logger),
) -> ConversationSummary:
    conversation = await conversation_store.create_conversation(user_id)
    await audit.log_async(user_id, "conversation.create", target=conversation.id, request=request)
    return conversation


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation_endpoint(
    conversation_id: str,
    conversation_store: ConversationStore = Depends(get_store),
    user_id: str = Depends(get_current_user_id),
) -> ConversationDetail:
    try:
        return await conversation_store.get_conversation(conversation_id, user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found.") from exc


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation_endpoint(
    request: Request,
    conversation_id: str,
    conversation_store: ConversationStore = Depends(get_store),
    user_id: str = Depends(get_current_user_id),
    audit: AuditLogger = Depends(get_audit_logger),
) -> Response:
    if not await conversation_store.delete_conversation(conversation_id, user_id):
        await audit.log_async(
            user_id,
            "conversation.delete",
            target=conversation_id,
            result="denied",
            request=request,
        )
        raise HTTPException(status_code=404, detail="Conversation not found.")
    await audit.log_async(user_id, "conversation.delete", target=conversation_id, request=request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/conversations/{conversation_id}/messages/stream")
async def stream_conversation_message(
    conversation_id: str,
    payload: ChatStreamRequest,
    request: Request,
    conversation_store: ConversationStore = Depends(get_store),
    chat_runtime: SupportsStreamingReply = Depends(get_runtime),
    user_id: str = Depends(get_current_user_id),
    audit: AuditLogger = Depends(get_audit_logger),
) -> StreamingResponse:
    if not await conversation_store.conversation_exists(conversation_id, user_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")

    user_message = await conversation_store.save_user_message(
        conversation_id, user_id, payload.message
    )
    conversation = await conversation_store.get_conversation(conversation_id, user_id)
    summary = await conversation_store.get_conversation_summary(conversation_id, user_id)
    await audit.log_async(
        user_id,
        "conversation.stream",
        target=conversation_id,
        detail={"mode": payload.mode, "message_chars": len(payload.message)},
        request=request,
    )

    async def agent_event_stream() -> AsyncIterator[str]:
        yield sse_event(
            "message_start",
            MessageStartPayload(conversation=summary, user_message=user_message).model_dump(
                mode="json"
            ),
        )

        step_queue: asyncio.Queue[AgentStep] = asyncio.Queue()

        async def on_step(step: AgentStep) -> None:
            await step_queue.put(step)

        agent = AgentLoop(
            chat_runtime,
            registry=_app_compat().get_web_agent_registry(),
            system_protocol=READ_ONLY_EMAIL_PROTOCOL,
            enforce_schema=request.app.state.settings.open_model_agent_constrained_decoding,
        )
        run_task = asyncio.create_task(
            agent.run(
                payload.message,
                system_prompt=payload.system_prompt,
                max_steps=payload.max_steps,
                on_step=on_step,
                user_id=user_id,
                on_tool_call=lambda tool_name, arguments: audit_agent_tool_call(
                    audit, user_id, tool_name, arguments, request
                ),
            )
        )

        try:
            while not run_task.done():
                if await request.is_disconnected():
                    run_task.cancel()
                    return
                try:
                    step = await asyncio.wait_for(step_queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue
                yield sse_event("agent_step", step.model_dump(mode="json"))

            while not step_queue.empty():
                step = step_queue.get_nowait()
                yield sse_event("agent_step", step.model_dump(mode="json"))

            result = await run_task
            if result.stopped_reason == "error":
                yield sse_event("error", ErrorPayload(message=result.answer).model_dump(mode="json"))
                return

            assistant_message = await conversation_store.save_assistant_message(
                conversation_id,
                user_id,
                result.answer,
                sources=[],
            )
            updated_summary = await conversation_store.get_conversation_summary(
                conversation_id, user_id
            )
            yield sse_event(
                "message_complete",
                MessageCompletePayload(
                    conversation=updated_summary,
                    assistant_message=assistant_message,
                ).model_dump(mode="json"),
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not run_task.done():
                run_task.cancel()
                with suppress(asyncio.CancelledError):
                    await run_task
            yield sse_event("error", ErrorPayload(message=str(exc)).model_dump(mode="json"))

    if payload.mode == "agent":
        return _stream_response(agent_event_stream())

    async def event_stream() -> AsyncIterator[str]:
        yield sse_event(
            "message_start",
            MessageStartPayload(conversation=summary, user_message=user_message).model_dump(
                mode="json"
            ),
        )

        steps = build_steps(payload.mode)
        if steps:
            first_step_id, first_step_label = steps[0]
            yield sse_event(
                "step_update",
                StepUpdatePayload(
                    step_id=first_step_id, label=first_step_label, status="active"
                ).model_dump(mode="json"),
            )

        generation = None
        assistant_chunks: list[str] = []
        try:
            for step_id, step_label in steps[:-1]:
                yield sse_event(
                    "step_update",
                    StepUpdatePayload(
                        step_id=step_id, label=step_label, status="complete"
                    ).model_dump(mode="json"),
                )

            if steps:
                draft_step_id, draft_step_label = steps[-1]
                yield sse_event(
                    "step_update",
                    StepUpdatePayload(
                        step_id=draft_step_id, label=draft_step_label, status="active"
                    ).model_dump(mode="json"),
                )

            generation = chat_runtime.stream_reply(
                messages=[message.model_dump() for message in conversation.messages],
                system_prompt=(payload.system_prompt or DEFAULT_SYSTEM_PROMPT).strip(),
                mode=payload.mode,
            )

            for chunk in generation.chunks:
                if await request.is_disconnected():
                    generation.cancel()
                    return
                assistant_chunks.append(chunk)
                yield sse_event(
                    "assistant_delta",
                    AssistantDeltaPayload(delta=chunk).model_dump(mode="json"),
                )

            assistant_text = "".join(assistant_chunks).strip()
            if not assistant_text:
                raise RuntimeError("The model returned an empty response.")

            assistant_message = await conversation_store.save_assistant_message(
                conversation_id,
                user_id,
                assistant_text,
                sources=[],
            )
            updated_summary = await conversation_store.get_conversation_summary(
                conversation_id, user_id
            )

            if len(steps) > 1:
                draft_step_id, draft_step_label = steps[-1]
                yield sse_event(
                    "step_update",
                    StepUpdatePayload(
                        step_id=draft_step_id, label=draft_step_label, status="complete"
                    ).model_dump(mode="json"),
                )

            yield sse_event(
                "message_complete",
                MessageCompletePayload(
                    conversation=updated_summary,
                    assistant_message=assistant_message,
                ).model_dump(mode="json"),
            )
        except Exception as exc:
            if generation is not None:
                generation.cancel()
            yield sse_event("error", ErrorPayload(message=str(exc)).model_dump(mode="json"))

    return _stream_response(event_stream())


def _stream_response(events: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        events,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
