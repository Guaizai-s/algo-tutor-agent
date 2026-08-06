"""讨论区 Pydantic Schema (API 契约, Task 15)。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.models.discussion import DiscussionCategory
from app.schemas.common import BaseSchema, PageParams, PageResponse

# ── Discussion ──


class DiscussionCreate(BaseSchema):
    title: str = Field(..., min_length=1, max_length=300)
    content: str = Field(..., min_length=1)
    category: DiscussionCategory = DiscussionCategory.GENERAL
    knowledge_id: UUID | None = None
    problem_id: UUID | None = None


class DiscussionUpdate(BaseSchema):
    title: str | None = Field(None, min_length=1, max_length=300)
    content: str | None = Field(None, min_length=1)
    category: DiscussionCategory | None = None


class DiscussionRead(BaseSchema):
    id: UUID
    author_id: UUID
    title: str
    content: str
    category: DiscussionCategory
    knowledge_id: UUID | None
    problem_id: UUID | None
    is_pinned: bool
    view_count: int
    like_count: int
    comment_count: int
    created_at: datetime
    updated_at: datetime


class DiscussionListParams(PageParams):
    category: DiscussionCategory | None = None
    knowledge_id: UUID | None = None
    problem_id: UUID | None = None


class DiscussionListResponse(PageResponse[DiscussionRead]):
    pass


# ── DiscussionComment ──


class DiscussionCommentCreate(BaseSchema):
    content: str = Field(..., min_length=1)
    parent_id: UUID | None = None


class DiscussionCommentRead(BaseSchema):
    id: UUID
    discussion_id: UUID
    author_id: UUID
    content: str
    parent_id: UUID | None
    created_at: datetime
    updated_at: datetime
    replies: list[DiscussionCommentRead] = Field(default_factory=list)


class DiscussionDetailResponse(DiscussionRead):
    comments: list[DiscussionCommentRead] = Field(default_factory=list)
