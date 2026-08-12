"""RAGService: knowledge retrieval.

Strategy:
1. Try pgvector semantic search using OpenAI embeddings.
2. If embeddings are unavailable (no column / no API key / embedding error),
   fall back to ILIKE keyword search.
3. Never fabricate vectors or references.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.models.knowledge import KnowledgePoint, Lecture, LectureLevel

if TYPE_CHECKING:
    from app.services.openai_service import OpenAIService

logger = logging.getLogger(__name__)


class RAGService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        openai_svc: OpenAIService | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._openai = openai_svc
        self._pgvector_available: bool | None = None  # cached check

    async def search(
        self,
        query: str,
        level: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Return knowledge snippets. Empty list on no results."""
        limit = max(1, min(limit, settings.RAG_MAX_LIMIT))

        embedding = await self._embed(query)
        if embedding is not None and await self._pgvector_ready():
            results = await self._semantic_search(embedding, level, limit)
            if results:
                return results
            # fall through to keyword fallback if semantic returned nothing

        return await self._keyword_fallback(query, level, limit)

    async def _embed(self, text: str) -> list[float] | None:
        """Call OpenAI embeddings. Returns None on any failure."""
        if self._openai is None:
            return None
        try:
            resp = await self._openai.client.embeddings.create(
                model=settings.RAG_EMBEDDING_MODEL,
                input=text,
            )
            return list(resp.data[0].embedding)
        except Exception as exc:
            logger.warning("embedding failed, degrading to keyword search: %s", type(exc).__name__)
            return None

    async def _pgvector_ready(self) -> bool:
        """Check whether the lectures.embedding column exists and has rows."""
        if self._pgvector_available is not None:
            return self._pgvector_available
        try:
            async with self._session_factory() as session:
                result = await session.execute(
                    text(
                        "SELECT EXISTS ("
                        "  SELECT 1 FROM information_schema.columns "
                        "  WHERE table_name='lectures' AND column_name='embedding'"
                        ") AS has_col"
                    )
                )
                has_col = result.scalar()
                if not has_col:
                    self._pgvector_available = False
                    return False
                result = await session.execute(
                    text("SELECT EXISTS (SELECT 1 FROM lectures WHERE embedding IS NOT NULL) AS has_data")
                )
                self._pgvector_available = bool(result.scalar())
                return self._pgvector_available
        except Exception as exc:
            logger.warning("pgvector readiness check failed: %s", type(exc).__name__)
            self._pgvector_available = False
            return False

    async def _semantic_search(
        self,
        embedding: list[float],
        level: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Use pgvector cosine distance. Returns [] on any failure."""
        try:
            async with self._session_factory() as session:
                # Use CAST(:vec AS vector) — the `::vector` syntax breaks
                # SQLAlchemy text() bind param parsing (it treats `:vec::vector`
                # as a param named `ve`).
                vec_literal = "[" + ",".join(str(float(x)) for x in embedding) + "]"
                sql = (
                    "SELECT l.id AS lecture_id, l.title AS lecture_title, l.level AS level, "
                    "l.content AS content, k.id AS knowledge_id, k.name AS knowledge_name, "
                    "1 - (l.embedding <=> CAST(:vec AS vector)) AS score "
                    "FROM lectures l JOIN knowledge_points k ON k.id = l.knowledge_id "
                    "WHERE l.embedding IS NOT NULL "
                )
                params: dict[str, Any] = {"vec": vec_literal, "limit": limit}
                if level in ("card", "standard", "deep"):
                    sql += "AND l.level = :level "
                    params["level"] = level
                sql += "ORDER BY l.embedding <=> CAST(:vec AS vector) LIMIT :limit"

                result = await session.execute(text(sql), params)
                rows = result.mappings().all()
                return [
                    {
                        "knowledge_id": str(r["knowledge_id"]),
                        "knowledge_name": r["knowledge_name"],
                        "lecture_id": str(r["lecture_id"]),
                        "lecture_title": r["lecture_title"],
                        "level": r["level"],
                        "snippet": (r["content"] or "")[:600],
                        "source": "knowledge",
                        "score": float(r["score"]),
                    }
                    for r in rows
                ]
        except Exception as exc:
            logger.warning("semantic search failed, falling back: %s", type(exc).__name__)
            return []

    async def _keyword_fallback(
        self,
        query: str,
        level: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """ILIKE keyword search on knowledge_point.name / description / lecture.title / content."""
        like = f"%{query}%"
        async with self._session_factory() as session:
            stmt = (
                select(Lecture, KnowledgePoint)
                .join(KnowledgePoint, KnowledgePoint.id == Lecture.knowledge_id)
                .where(
                    or_(
                        KnowledgePoint.name.ilike(like),
                        KnowledgePoint.description.ilike(like),
                        Lecture.title.ilike(like),
                        Lecture.content.ilike(like),
                    )
                )
            )
            if level in ("card", "standard", "deep"):
                stmt = stmt.where(Lecture.level == LectureLevel(level))
            stmt = stmt.limit(limit)

            result = await session.execute(stmt)
            rows = result.all()

            out: list[dict[str, Any]] = []
            for lecture, kp in rows:
                out.append(
                    {
                        "knowledge_id": str(kp.id),
                        "knowledge_name": kp.name,
                        "lecture_id": str(lecture.id),
                        "lecture_title": lecture.title,
                        "level": lecture.level.value,
                        "snippet": (lecture.content or "")[:600],
                        "source": "knowledge",
                    }
                )
            return out


# Module-level singleton populated by lifespan in main.py.
rag_service: RAGService | None = None
