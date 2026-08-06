"""Authentication business logic."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.codeforces import CodeforcesAccount
from app.models.user import User
from app.schemas.auth import ProfileUpdateRequest, RegisterRequest
from app.services.codeforces.client import (
    CodeforcesClient,
    CodeforcesPermanentError,
)


class UserAlreadyExistsError(Exception):
    """Raised when an email address or username is already registered."""

    def __init__(self, field: str) -> None:
        self.field = field
        super().__init__(f"{field} already registered")


class CodeforcesHandleInvalidError(Exception):
    """Codeforces handle 不存在或格式无效。"""


class CodeforcesHandleAlreadyBoundError(Exception):
    """Codeforces handle 已被其他平台用户绑定。"""


class CodeforcesUnavailableError(Exception):
    """Codeforces API 暂时不可用。"""


class CodeforcesRebindRequiredError(Exception):
    """当前用户已经绑定了另一个 CF handle。"""


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


async def update_user_profile(db: AsyncSession, user: User, payload: ProfileUpdateRequest) -> User:
    """更新用户档案；仅修改请求中显式出现的字段。"""
    changes = payload.model_dump(exclude_unset=True)
    if "username" in changes and changes["username"] is not None:
        duplicate = (
            await db.execute(
                select(User.id).where(
                    User.username == changes["username"],
                    User.id != user.id,
                )
            )
        ).scalar_one_or_none()
        if duplicate is not None:
            raise UserAlreadyExistsError("username")

    for field, value in changes.items():
        setattr(user, field, value)

    try:
        await db.flush()
    except IntegrityError as exc:
        raise UserAlreadyExistsError("username") from exc
    await db.refresh(user)
    return user


async def get_codeforces_account(db: AsyncSession, user_id) -> CodeforcesAccount | None:
    return (
        await db.execute(select(CodeforcesAccount).where(CodeforcesAccount.user_id == user_id))
    ).scalar_one_or_none()


async def bind_codeforces_account(
    db: AsyncSession,
    user: User,
    handle: str,
    client: CodeforcesClient,
) -> CodeforcesAccount:
    """验证并绑定 CF handle，同时记录当前 rating。"""
    try:
        result = await client.user_info(handle)
    except CodeforcesPermanentError as exc:
        raise CodeforcesHandleInvalidError(handle) from exc
    except Exception as exc:
        raise CodeforcesUnavailableError(str(exc)) from exc

    if not result:
        raise CodeforcesHandleInvalidError(handle)

    info = result[0]
    canonical_handle = str(info.get("handle") or handle)
    existing_for_user = await get_codeforces_account(db, user.id)
    if existing_for_user is not None and existing_for_user.handle.lower() != canonical_handle.lower():
        raise CodeforcesRebindRequiredError(existing_for_user.handle)

    owner = (
        await db.execute(
            select(CodeforcesAccount).where(func.lower(CodeforcesAccount.handle) == canonical_handle.lower())
        )
    ).scalar_one_or_none()
    if owner is not None and owner.user_id != user.id:
        raise CodeforcesHandleAlreadyBoundError(canonical_handle)

    rating = info.get("rating")
    if existing_for_user is None:
        account = CodeforcesAccount(
            user_id=user.id,
            handle=canonical_handle,
            current_rating=int(rating) if rating is not None else None,
        )
        db.add(account)
    else:
        account = existing_for_user
        account.handle = canonical_handle
        if rating is not None:
            account.current_rating = int(rating)

    user.cf_handle = canonical_handle
    await db.flush()
    await db.refresh(account)
    await db.refresh(user)
    return account
