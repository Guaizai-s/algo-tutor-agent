"""Authentication business logic."""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.user import User
from app.schemas.auth import BindCFResponse, ProfileUpdateRequest, RegisterRequest
from app.services.codeforces.client import (
    CodeforcesPermanentError,
    close_codeforces_client,
    get_codeforces_client,
)


class UserAlreadyExistsError(Exception):
    """Raised when an email address or username is already registered."""

    def __init__(self, field: str) -> None:
        self.field = field
        super().__init__(f"{field} already registered")


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    normalized_email = email.strip().lower()
    result = await db.execute(select(User).where(User.email == normalized_email))
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, payload: RegisterRequest) -> User:
    existing = (
        await db.execute(
            select(User.email, User.username).where(
                or_(User.email == str(payload.email), User.username == payload.username)
            )
        )
    ).first()
    if existing is not None:
        field = "email" if existing.email == str(payload.email) else "username"
        raise UserAlreadyExistsError(field)

    user = User(
        email=str(payload.email),
        username=payload.username,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:
        # A concurrent registration can pass the pre-check and lose the
        # unique-index race. The request transaction will be rolled back by
        # get_db after the endpoint translates this domain error to HTTP 409.
        raise UserAlreadyExistsError("email or username") from exc
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User | None:
    user = await get_user_by_email(db, email)
    if user is None or not verify_password(password, user.hashed_password):
        return None
    return user


async def update_profile(
    db: AsyncSession,
    user: User,
    payload: ProfileUpdateRequest,
) -> User:
    """更新用户 ACM 档案字段（部分更新，只设非 None 字段）。"""
    if payload.school is not None:
        user.school = payload.school
    if payload.cf_handle is not None:
        user.cf_handle = payload.cf_handle
    if payload.atcoder_handle is not None:
        user.atcoder_handle = payload.atcoder_handle
    if payload.target_medal is not None:
        user.target_medal = payload.target_medal
    await db.flush()
    await db.refresh(user)
    return user


async def bind_cf_handle(
    db: AsyncSession,
    user: User,
    handle: str,
    cf_client=None,
) -> BindCFResponse:
    """绑定 CF handle：调用 CF API 验证 handle 存在，拉取初始数据。

    Args:
        db: 数据库会话
        user: 当前用户
        handle: CF handle
        cf_client: CodeforcesClient 实例（可选，不传则自动创建）

    Returns:
        BindCFResponse: 绑定结果含 rating 信息

    Raises:
        ValueError: CF handle 不存在
        CodeforcesAPIError: CF API 调用失败
    """
    should_close = False
    if cf_client is None:
        cf_client = get_codeforces_client()
        should_close = True

    try:
        # 验证 handle 是否存在
        user_info_list = await cf_client.user_info(handle)
        if not user_info_list:
            raise ValueError(f"Codeforces handle '{handle}' 不存在")

        info = user_info_list[0]
        user.cf_handle = handle

        # 同步到 CodeforcesAccount 表
        from app.models.codeforces import CodeforcesAccount

        existing = (
            await db.execute(select(CodeforcesAccount).where(CodeforcesAccount.user_id == user.id))
        ).scalar_one_or_none()
        if existing is None:
            existing = CodeforcesAccount(
                user_id=user.id,
                handle=handle,
                current_rating=info.get("rating"),
            )
            db.add(existing)
        else:
            existing.handle = handle
            existing.current_rating = info.get("rating")

        await db.flush()
        await db.refresh(user)

        return BindCFResponse(
            handle=handle,
            current_rating=info.get("rating"),
            max_rating=info.get("maxRating"),
            rank=info.get("rank"),
            message="CF handle 绑定成功",
        )
    except (CodeforcesPermanentError, ValueError) as exc:
        raise ValueError(str(exc)) from exc
    finally:
        if should_close:
            await close_codeforces_client(cf_client)
