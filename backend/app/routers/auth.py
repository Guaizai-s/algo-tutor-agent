"""Registration, login, and current-user API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CodeforcesClientDep, CurrentUser
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.auth import (
    CodeforcesAccountRead,
    CodeforcesBindRequest,
    CodeforcesBindResponse,
    LoginRequest,
    ProfileUpdateRequest,
    RegisterRequest,
    TokenResponse,
    UserRead,
)
from app.services.auth import (
    CodeforcesHandleAlreadyBoundError,
    CodeforcesHandleInvalidError,
    CodeforcesRebindRequiredError,
    CodeforcesUnavailableError,
    UserAlreadyExistsError,
    authenticate_user,
    bind_codeforces_account,
    create_user,
    get_codeforces_account,
    update_user_profile,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(user: User) -> TokenResponse:
    token = create_access_token(user.id, extra_claims={"role": user.role.value})
    return TokenResponse(access_token=token, user=UserRead.model_validate(user))


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    try:
        user = await create_user(db, payload)
    except UserAlreadyExistsError as exc:
        label = "邮箱" if exc.field == "email" else "用户名" if exc.field == "username" else "邮箱或用户名"
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"{label}已被注册") from exc
    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    user = await authenticate_user(db, str(payload.email), payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _token_response(user)


@router.get("/me", response_model=UserRead)
async def get_me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)


@router.patch("/profile", response_model=UserRead)
async def update_profile(
    payload: ProfileUpdateRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> UserRead:
    try:
        user = await update_user_profile(db, current_user, payload)
    except UserAlreadyExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已被注册") from exc
    return UserRead.model_validate(user)


@router.get("/codeforces", response_model=CodeforcesAccountRead | None)
async def get_codeforces_binding(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> CodeforcesAccountRead | None:
    account = await get_codeforces_account(db, current_user.id)
    return CodeforcesAccountRead.model_validate(account) if account is not None else None


@router.post("/codeforces/bind", response_model=CodeforcesBindResponse)
async def bind_codeforces(
    payload: CodeforcesBindRequest,
    current_user: CurrentUser,
    client: CodeforcesClientDep,
    db: AsyncSession = Depends(get_db),
) -> CodeforcesBindResponse:
    try:
        account = await bind_codeforces_account(db, current_user, payload.handle, client)
    except CodeforcesHandleInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Codeforces 用户不存在") from exc
    except CodeforcesHandleAlreadyBoundError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该 Codeforces 账号已被绑定") from exc
    except CodeforcesRebindRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"当前账号已绑定 {exc.args[0]}，MVP 阶段暂不支持换绑",
        ) from exc
    except CodeforcesUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Codeforces API 暂不可用") from exc

    return CodeforcesBindResponse(
        user=UserRead.model_validate(current_user),
        account=CodeforcesAccountRead.model_validate(account),
    )
