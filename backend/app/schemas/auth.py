"""Request and response schemas for user authentication."""

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.user import TargetMedal, UserRole

# 基本邮箱格式校验，比 EmailStr 宽松，允许 .local 等内部域名
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _validate_email(value: str) -> str:
    """基本邮箱格式校验：允许内部域名（如 .local）。"""
    normalized = value.strip().lower()
    if not _EMAIL_RE.match(normalized):
        raise ValueError("invalid email format")
    return normalized


class RegisterRequest(BaseModel):
    email: str
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _validate_email(value)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("username must contain at least 2 non-whitespace characters")
        return normalized

    @field_validator("password")
    @classmethod
    def validate_bcrypt_length(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("password must not exceed 72 UTF-8 bytes")
        return value


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _validate_email(value)


class UserRead(BaseModel):
    id: UUID
    email: str
    username: str
    role: UserRole
    avatar: str | None
    school: str | None
    cf_handle: str | None
    atcoder_handle: str | None
    target_medal: TargetMedal | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead
