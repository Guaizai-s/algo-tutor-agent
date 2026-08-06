"""最小冷启动路由。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CodeforcesClientDep, CurrentUser
from app.schemas.onboarding import ColdStartResponse, DiagnosticSubmitRequest
from app.services.learning_path import CycleDetectedError
from app.services.onboarding import get_onboarding_status, start_cold_start, submit_diagnostic

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("/status", response_model=ColdStartResponse)
async def api_get_onboarding_status(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> ColdStartResponse:
    return await get_onboarding_status(db, current_user)


@router.post("/start", response_model=ColdStartResponse)
async def api_start_onboarding(
    current_user: CurrentUser,
    client: CodeforcesClientDep,
    db: AsyncSession = Depends(get_db),
) -> ColdStartResponse:
    try:
        return await start_cold_start(db, current_user, client)
    except CycleDetectedError as exc:
        raise HTTPException(status_code=422, detail="知识点依赖图存在环，无法生成学习路径") from exc


@router.post("/diagnostic", response_model=ColdStartResponse)
async def api_submit_diagnostic(
    payload: DiagnosticSubmitRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> ColdStartResponse:
    try:
        return await submit_diagnostic(db, current_user, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except CycleDetectedError as exc:
        raise HTTPException(status_code=422, detail="知识点依赖图存在环，无法生成学习路径") from exc
