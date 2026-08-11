"""OpenAI service singleton.

Holds the AsyncOpenAI client. Created once in the app lifespan.
The API key never leaves the server process.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class OpenAIService:
    def __init__(self) -> None:
        # Import lazily so tests that don't touch OpenAI can skip the SDK.
        from openai import AsyncOpenAI

        if not settings.OPENAI_API_KEY:
            logger.warning("OPENAI_API_KEY not set; agent endpoints will return 503")

        self.client: AsyncOpenAI = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY or "missing",
            base_url=settings.OPENAI_BASE_URL,
            timeout=settings.OPENAI_REQUEST_TIMEOUT_SEC,
        )


# Module-level singleton populated by lifespan in main.py.
openai_service: OpenAIService | None = None


def get_openai() -> OpenAIService:
    """FastAPI dependency. Raises 503 if not initialized."""
    from fastapi import HTTPException

    if openai_service is None:
        raise HTTPException(status_code=503, detail="OpenAI service not ready")
    if not settings.OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="OpenAI API key not configured")
    return openai_service
