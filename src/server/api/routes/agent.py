from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from ....agent import AgentLoop, AgentRunRequest, AgentRunResult, ApprovalDecisionResult
from ....tools.ledger import SendLedger
from ...core.runtime import SupportsStreamingReply
from ...services.audit_service import AuditLogger
from ...services.chat_stream_service import audit_agent_tool_call
from ..deps import (
    get_audit_logger,
    get_current_user_id,
    get_runtime,
    get_send_ledger,
    tool_http_error,
    verify_tools_token,
)
router = APIRouter(dependencies=[Depends(verify_tools_token)])


@router.post("/agent/run", response_model=AgentRunResult)
async def agent_run_endpoint(
    request: Request,
    payload: AgentRunRequest,
    chat_runtime: SupportsStreamingReply = Depends(get_runtime),
    user_id: str = Depends(get_current_user_id),
    audit: AuditLogger = Depends(get_audit_logger),
) -> AgentRunResult:
    try:

        async def on_tool_call(tool_name: str, arguments: dict[str, object]) -> None:
            await audit_agent_tool_call(audit, user_id, tool_name, arguments, request)

        return await AgentLoop(
            chat_runtime,
            enforce_schema=request.app.state.settings.open_model_agent_constrained_decoding,
        ).run(
            payload.message,
            system_prompt=payload.system_prompt,
            max_steps=payload.max_steps,
            user_id=user_id,
            on_tool_call=on_tool_call,
        )
    except Exception as exc:
        raise tool_http_error(exc) from exc


@router.post("/agent/approvals/{approval_id}/approve", response_model=ApprovalDecisionResult)
async def agent_approval_approve_endpoint(
    approval_id: str,
    x_operator: str | None = Header(default=None),
    ledger: SendLedger = Depends(get_send_ledger),
) -> ApprovalDecisionResult:
    try:
        row = await ledger.decide_approval(approval_id, "approved", x_operator or "ops")
        return ApprovalDecisionResult(
            id=row.id,
            status=row.status,  # type: ignore[arg-type]
            decided_at=row.decided_at,
            decided_by=row.decided_by,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Approval not found.") from exc


@router.post("/agent/approvals/{approval_id}/reject", response_model=ApprovalDecisionResult)
async def agent_approval_reject_endpoint(
    approval_id: str,
    x_operator: str | None = Header(default=None),
    ledger: SendLedger = Depends(get_send_ledger),
) -> ApprovalDecisionResult:
    try:
        row = await ledger.decide_approval(approval_id, "rejected", x_operator or "ops")
        return ApprovalDecisionResult(
            id=row.id,
            status=row.status,  # type: ignore[arg-type]
            decided_at=row.decided_at,
            decided_by=row.decided_by,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Approval not found.") from exc
