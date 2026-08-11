"""Registration, login, and current-user API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import CurrentUser
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.auth import (
    BindCFRequest,
    BindCFResponse,
    LoginRequest,
    ProfileUpdateRequest,
    RegisterRequest,
    TokenResponse,
    UserRead,
)
from app.services.auth import (
    UserAlreadyExistsError,
    authenticate_user,
    bind_cf_handle,
    create_user,
    update_profile,
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
async def update_my_profile(
    payload: ProfileUpdateRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> UserRead:
    updated = await update_profile(db, current_user, payload)
    return UserRead.model_validate(updated)


@router.post("/bind-cf", response_model=BindCFResponse)
async def bind_codeforces(
    payload: BindCFRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> BindCFResponse:
    try:
        return await bind_cf_handle(db, current_user, payload.handle)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
