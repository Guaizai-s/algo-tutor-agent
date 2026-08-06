"""Seed admin user (idempotent).

Run from ``backend``:

    python -m scripts.seed_users

Creates admin@algo-tutor.local / admin123 if not exists.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.database import async_session_maker
from app.core.security import hash_password
from app.models.codeforces import Submission  # noqa: F401 — register Submission in mapper registry
from app.models.user import User, UserRole

ADMIN_EMAIL = "admin@algo-tutor.local"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"


async def seed() -> None:
    async with async_session_maker() as session:
        existing = (await session.execute(select(User).where(User.email == ADMIN_EMAIL))).scalar_one_or_none()

        if existing is not None:
            print(f"Admin user already exists: {existing.email} (id={existing.id})")
            return

        user = User(
            email=ADMIN_EMAIL,
            username=ADMIN_USERNAME,
            hashed_password=hash_password(ADMIN_PASSWORD),
            role=UserRole.ADMIN,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        print(f"Admin user created: {user.email} (id={user.id})")
        print(f"  Login: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(seed())
