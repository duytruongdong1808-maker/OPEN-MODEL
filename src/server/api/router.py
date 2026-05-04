from fastapi import APIRouter, Depends

from .deps import verify_tools_token
from .routes import agent, audit, conversations, gmail_auth, health, mail, system, tools


def create_api_router(*, protect_chat_routes: bool = True) -> APIRouter:
    api_router = APIRouter()
    chat_dependencies = [Depends(verify_tools_token)] if protect_chat_routes else []

    api_router.include_router(health.router)
    api_router.include_router(system.router)
    api_router.include_router(audit.login_router)
    api_router.include_router(audit.me_router, dependencies=chat_dependencies)
    api_router.include_router(gmail_auth.router)
    api_router.include_router(tools.router)
    api_router.include_router(mail.router, dependencies=chat_dependencies)
    api_router.include_router(agent.router)
    api_router.include_router(conversations.router, dependencies=chat_dependencies)
    return api_router
