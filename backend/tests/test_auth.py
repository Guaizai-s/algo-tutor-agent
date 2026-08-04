"""API and security regression tests for Task 2.1 authentication."""

from __future__ import annotations

from datetime import timedelta

import pytest
from jose import jwt
from sqlalchemy import select

from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User, UserRole


@pytest.mark.asyncio
async def test_register_returns_token_and_persists_hashed_password(client, db_session):
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "  Student@Example.com ", "username": " student_1 ", "password": "secret123"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == "student@example.com"
    assert body["user"]["username"] == "student_1"
    assert body["user"]["role"] == "student"
    assert "hashed_password" not in body["user"]

    user = (await db_session.execute(select(User).where(User.email == "student@example.com"))).scalar_one()
    assert user.hashed_password != "secret123"
    assert verify_password("secret123", user.hashed_password)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("first", "second", "detail"),
    [
        (
            {"email": "duplicate@example.com", "username": "first_user", "password": "secret123"},
            {"email": "DUPLICATE@example.com", "username": "second_user", "password": "secret123"},
            "邮箱已被注册",
        ),
        (
            {"email": "first@example.com", "username": "same_name", "password": "secret123"},
            {"email": "second@example.com", "username": "same_name", "password": "secret123"},
            "用户名已被注册",
        ),
    ],
)
async def test_register_rejects_duplicate_identity(client, first, second, detail):
    assert (await client.post("/api/v1/auth/register", json=first)).status_code == 201

    response = await client.post("/api/v1/auth/register", json=second)

    assert response.status_code == 409
    assert response.json()["detail"] == detail


@pytest.mark.asyncio
async def test_login_returns_token_and_user(client, db_session):
    user = User(
        email="login@example.com",
        username="login_user",
        hashed_password=hash_password("correct-password"),
        role=UserRole.STUDENT,
    )
    db_session.add(user)
    await db_session.flush()

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "LOGIN@example.com", "password": "correct-password"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["id"] == str(user.id)
    claims = jwt.decode(
        body["access_token"],
        settings.JWT_SECRET,
        algorithms=[settings.JWT_ALGORITHM],
    )
    assert claims["sub"] == str(user.id)
    assert claims["role"] == "student"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("missing@example.com", "wrong-password"),
        ("login@example.com", "wrong-password"),
    ],
)
async def test_login_rejects_invalid_credentials(client, db_session, email, password):
    db_session.add(
        User(
            email="login@example.com",
            username="login_user",
            hashed_password=hash_password("correct-password"),
        )
    )
    await db_session.flush()

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["detail"] == "邮箱或密码错误"


@pytest.mark.asyncio
async def test_me_returns_authenticated_user(client, db_session):
    user = User(
        email="me@example.com",
        username="me_user",
        hashed_password=hash_password("secret123"),
    )
    db_session.add(user)
    await db_session.flush()
    token = create_access_token(user.id)

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(user.id)
    assert response.json()["email"] == "me@example.com"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "authorization",
    [
        None,
        "Basic abc",
        "Bearer invalid-token",
    ],
)
async def test_me_rejects_missing_or_invalid_token(client, authorization):
    headers = {"Authorization": authorization} if authorization else {}

    response = await client.get("/api/v1/auth/me", headers=headers)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_me_rejects_expired_token(client, db_session):
    user = User(
        email="expired@example.com",
        username="expired_user",
        hashed_password=hash_password("secret123"),
    )
    db_session.add(user)
    await db_session.flush()
    token = create_access_token(user.id, expires_delta=timedelta(seconds=-1))

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_rejects_token_with_non_uuid_subject(client):
    token = create_access_token("not-a-uuid")

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email", "username": "valid_name", "password": "secret123"},
        {"email": "valid@example.com", "username": " ", "password": "secret123"},
        {"email": "valid@example.com", "username": "valid_name", "password": "short"},
        {"email": "valid@example.com", "username": "valid_name", "password": "密" * 25},
    ],
)
async def test_register_validates_input(client, payload):
    response = await client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 422
