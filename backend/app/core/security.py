"""Security utilities: password hashing + JWT (Task 2.1).

依赖（requirements.txt 已声明）：
- bcrypt（直接使用，不经过 passlib，因 passlib 1.7.4 与 bcrypt 5.x 不兼容）
- python-jose[cryptography]==3.3.0 用于 JWT 签发/校验

设计：
- 密码哈希用 bcrypt（含自动 salt + cost factor 12）
- JWT 用 HS256（settings.JWT_ALGORITHM），secret 从 settings.JWT_SECRET 读
- access_token 中 subject 存 user.id（UUID 字符串），exp 用 UTC

兼容性说明：
- bcrypt 5.0 移除了 passlib 依赖的 `__about__` 属性，passlib 1.7.4 的兼容
  检测代码会抛 AttributeError，导致 hash/verify 失败。
- 我们直接使用 bcrypt 的 hashpw/checkpw，避免引入 passlib。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

# bcrypt cost factor：12 是合理默认（不算慢，安全性足够）
BCRYPT_COST_FACTOR = 12


def hash_password(plain: str) -> str:
    """对明文密码做 bcrypt 哈希。

    bcrypt 限制密码最长 72 bytes。调用方应在输入校验阶段拒绝超长密码；
    此处再次防御，避免静默截断造成不同密码得到相同哈希语义。
    """
    pw_bytes = plain.encode("utf-8")
    if len(pw_bytes) > 72:
        raise ValueError("password must not exceed 72 UTF-8 bytes")
    salt = bcrypt.gensalt(rounds=BCRYPT_COST_FACTOR)
    return bcrypt.hashpw(pw_bytes, salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """校验明文密码与已存哈希是否匹配。

    任何异常（如哈希格式非法）都返回 False，避免抛错泄露内部信息。
    """
    try:
        pw_bytes = plain.encode("utf-8")
        if len(pw_bytes) > 72:
            return False
        hashed_bytes = hashed.encode("utf-8")
        return bcrypt.checkpw(pw_bytes, hashed_bytes)
    except Exception:
        return False


def create_access_token(
    subject: str | UUID,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """签发 JWT access token。

    Args:
        subject: 用户 ID（UUID 字符串）
        expires_delta: 自定义过期时长；None 则用 settings.ACCESS_TOKEN_EXPIRE_MINUTES
        extra_claims: 额外 claims（如 role），可选

    Returns:
        编码后的 JWT 字符串
    """
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    payload: dict[str, Any] = {
        "sub": str(subject),
        "exp": expire,
        "iat": now,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """解码并校验 JWT。

    Raises:
        JWTError: token 过期、签名非法、格式错误等
    """
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


def decode_access_token_or_none(token: str) -> dict[str, Any] | None:
    """解码 JWT，失败返回 None（不抛错）。"""
    try:
        return decode_access_token(token)
    except JWTError:
        return None
