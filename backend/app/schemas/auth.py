"""Request and response schemas for user authentication."""

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.user import TargetMedal, UserRole

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_CF_HANDLE_RE = re.compile(r"[A-Za-z0-9_.-]+")


def _validate_email(value: str) -> str:
    normalized = value.strip().lower()
    if not _EMAIL_RE.fullmatch(normalized):
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


class ProfileUpdateRequest(BaseModel):
    """Fields users may update without going through a provider binding flow."""

    username: str | None = Field(default=None, min_length=2, max_length=64)
    avatar: str | None = Field(default=None, max_length=512)
    school: str | None = Field(default=None, max_length=255)
    atcoder_handle: str | None = Field(default=None, max_length=64)
    target_medal: TargetMedal | None = None

    @field_validator("username")
    @classmethod
    def normalize_profile_username(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("username cannot be null")
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("username must contain at least 2 non-whitespace characters")
        return normalized

    @field_validator("avatar", "school", "atcoder_handle")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class BindCFRequest(BaseModel):
    handle: str = Field(min_length=3, max_length=24)

    @field_validator("handle")
    @classmethod
    def normalize_handle(cls, value: str) -> str:
        normalized = value.strip()
        if not _CF_HANDLE_RE.fullmatch(normalized):
            raise ValueError("invalid Codeforces handle format")
        return normalized


class BindCFResponse(BaseModel):
    handle: str
    current_rating: int | None
    max_rating: int | None
    rank: str | None
    message: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead
