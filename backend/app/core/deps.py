"""FastAPI dependencies for authentication (Task 2.1).

提供 get_current_user 依赖，从 Authorization header 解析 JWT 并加载用户。
其他需要鉴权的路由可通过 Depends(get_current_user) 注入当前用户。
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token_or_none
from app.models.user import User


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
) -> User:
    """从 Authorization: Bearer <token> 解析 JWT 并返回 User。

    Raises:
        HTTPException 401: 缺少 header、token 格式错误、token 过期、用户不存在
    """
    creds_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not authorization or not authorization.lower().startswith("bearer "):
        raise creds_error

    token = authorization.split(" ", 1)[1].strip()
    payload = decode_access_token_or_none(token)
    if payload is None:
        raise creds_error

    sub = payload.get("sub")
    if not sub:
        raise creds_error

    try:
        user_id = UUID(str(sub))
    except (ValueError, TypeError, AttributeError) as exc:
        raise creds_error from exc

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise creds_error

    return user


# 类型别名，便于路由签名
CurrentUser = Annotated[User, Depends(get_current_user)]
