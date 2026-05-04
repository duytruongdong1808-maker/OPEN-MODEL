from __future__ import annotations

from fastapi import APIRouter

from ....utils import get_hardware_profile

router = APIRouter()


@router.get("/system/info")
def system_info() -> dict[str, object]:
    profile = get_hardware_profile()
    return dict(profile)
