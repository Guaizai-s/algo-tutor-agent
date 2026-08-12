"""讨论区 service (Task 15)。"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.discussion import Discussion, DiscussionComment
from app.schemas.discussion import (
    DiscussionCommentCreate,
    DiscussionCommentRead,
    DiscussionCreate,
    DiscussionDetailResponse,
    DiscussionListParams,
    DiscussionListResponse,
    DiscussionRead,
    DiscussionUpdate,
)


def _comment_to_tree(comments: list[DiscussionComment]) -> list[DiscussionCommentRead]:
    """将扁平评论列表转为嵌套树结构。"""
    comment_map: dict[UUID, DiscussionCommentRead] = {}
    roots: list[DiscussionCommentRead] = []

    for c in comments:
        node = DiscussionCommentRead(
            id=c.id,
            discussion_id=c.discussion_id,
            author_id=c.author_id,
            content=c.content,
            parent_id=c.parent_id,
            created_at=c.created_at,
            updated_at=c.updated_at,
            replies=[],
        )
        comment_map[c.id] = node

    for c in comments:
        node = comment_map[c.id]
        if c.parent_id and c.parent_id in comment_map:
            comment_map[c.parent_id].replies.append(node)
        else:
            roots.append(node)

    return roots


# ── Discussion CRUD ──


async def list_discussions(db: AsyncSession, params: DiscussionListParams) -> DiscussionListResponse:
    filters = []
    if params.category:
        filters.append(Discussion.category == params.category)
    if params.knowledge_id:
        filters.append(Discussion.knowledge_id == params.knowledge_id)
    if params.problem_id:
        filters.append(Discussion.problem_id == params.problem_id)

    count_stmt = select(func.count(Discussion.id)).where(*filters)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(Discussion)
        .where(*filters)
        .order_by(Discussion.is_pinned.desc(), Discussion.created_at.desc())
        .offset((params.page - 1) * params.page_size)
        .limit(params.page_size)
    )
    rows = (await db.execute(stmt)).scalars().all()

    return DiscussionListResponse(
        items=[DiscussionRead.model_validate(r) for r in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=max(1, (total + params.page_size - 1) // params.page_size),
    )


async def get_discussion(db: AsyncSession, discussion_id: UUID) -> DiscussionDetailResponse | None:
    stmt = select(Discussion).where(Discussion.id == discussion_id).options(selectinload(Discussion.comments))
    discussion = (await db.execute(stmt)).scalar_one_or_none()
    if discussion is None:
        return None

    # 增加浏览计数
    await db.execute(
        update(Discussion).where(Discussion.id == discussion_id).values(view_count=Discussion.view_count + 1)
    )

    return DiscussionDetailResponse(
        id=discussion.id,
        author_id=discussion.author_id,
        title=discussion.title,
        content=discussion.content,
        category=discussion.category,
        knowledge_id=discussion.knowledge_id,
        problem_id=discussion.problem_id,
        is_pinned=discussion.is_pinned,
        view_count=discussion.view_count + 1,
        like_count=discussion.like_count,
        comment_count=discussion.comment_count,
        created_at=discussion.created_at,
        updated_at=discussion.updated_at,
        comments=_comment_to_tree(list(discussion.comments)),
    )


async def create_discussion(db: AsyncSession, author_id: UUID, data: DiscussionCreate) -> DiscussionRead:
    discussion = Discussion(
        author_id=author_id,
        title=data.title,
        content=data.content,
        category=data.category,
        knowledge_id=data.knowledge_id,
        problem_id=data.problem_id,
    )
    db.add(discussion)
    await db.flush()
    await db.refresh(discussion)
    return DiscussionRead.model_validate(discussion)


async def update_discussion(
    db: AsyncSession, discussion_id: UUID, author_id: UUID, data: DiscussionUpdate
) -> DiscussionRead | None:
    discussion = (
        await db.execute(select(Discussion).where(Discussion.id == discussion_id, Discussion.author_id == author_id))
    ).scalar_one_or_none()
    if discussion is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(discussion, key, value)
    await db.flush()
    await db.refresh(discussion)
    return DiscussionRead.model_validate(discussion)


async def delete_discussion(db: AsyncSession, discussion_id: UUID, author_id: UUID) -> bool:
    discussion = (
        await db.execute(select(Discussion).where(Discussion.id == discussion_id, Discussion.author_id == author_id))
    ).scalar_one_or_none()
    if discussion is None:
        return False
    await db.delete(discussion)
    await db.flush()
    return True


async def like_discussion(db: AsyncSession, discussion_id: UUID) -> DiscussionRead | None:
    discussion = (await db.execute(select(Discussion).where(Discussion.id == discussion_id))).scalar_one_or_none()
    if discussion is None:
        return None
    discussion.like_count += 1
    await db.flush()
    await db.refresh(discussion)
    return DiscussionRead.model_validate(discussion)


# ── DiscussionComment CRUD ──


async def create_comment(
    db: AsyncSession, discussion_id: UUID, author_id: UUID, data: DiscussionCommentCreate
) -> DiscussionCommentRead | None:
    # 验证 discussion 存在
    exists = (await db.execute(select(Discussion.id).where(Discussion.id == discussion_id))).scalar_one_or_none()
    if exists is None:
        return None

    # 验证 parent_id 存在且属于同一 discussion
    if data.parent_id:
        parent = (
            await db.execute(
                select(DiscussionComment).where(
                    DiscussionComment.id == data.parent_id,
                    DiscussionComment.discussion_id == discussion_id,
                )
            )
        ).scalar_one_or_none()
        if parent is None:
            return None

    comment = DiscussionComment(
        discussion_id=discussion_id,
        author_id=author_id,
        content=data.content,
        parent_id=data.parent_id,
    )
    db.add(comment)

    # 更新讨论的 comment_count
    await db.execute(
        update(Discussion).where(Discussion.id == discussion_id).values(comment_count=Discussion.comment_count + 1)
    )

    await db.flush()
    await db.refresh(comment)
    return DiscussionCommentRead(
        id=comment.id,
        discussion_id=comment.discussion_id,
        author_id=comment.author_id,
        content=comment.content,
        parent_id=comment.parent_id,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
        replies=[],
    )


async def delete_comment(db: AsyncSession, comment_id: UUID, discussion_id: UUID, author_id: UUID) -> bool:
    comment = (
        await db.execute(
            select(DiscussionComment).where(
                DiscussionComment.id == comment_id,
                DiscussionComment.discussion_id == discussion_id,
                DiscussionComment.author_id == author_id,
            )
        )
    ).scalar_one_or_none()
    if comment is None:
        return False

    await db.delete(comment)
    # 更新讨论的 comment_count（包括已被删除的子回复）
    await db.execute(
        update(Discussion).where(Discussion.id == discussion_id).values(comment_count=Discussion.comment_count - 1)
    )
    await db.flush()
    return True
