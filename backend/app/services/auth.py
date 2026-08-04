"""Authentication business logic."""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.user import User
from app.schemas.auth import RegisterRequest


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
