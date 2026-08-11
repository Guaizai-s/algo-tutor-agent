"""Knowledge 相关 Pydantic Schema (API 契约)。"""

from uuid import UUID

from app.models.knowledge import KnowledgePointDifficulty, LectureLevel
from app.schemas.common import BaseSchema


class KnowledgePointRead(BaseSchema):
    id: UUID
    name: str
    slug: str
    description: str | None
    difficulty: KnowledgePointDifficulty
    parent_id: UUID | None
    order: int
    # 聚合统计（list 接口返回，单点接口也返回）
    lecture_count: int = 0
    template_count: int = 0
    children_count: int = 0
    # Codeforces 关联
    cf_tag: str | None = None
    cf_problem_count: int = 0


class LectureRead(BaseSchema):
    id: UUID
    knowledge_id: UUID
    level: LectureLevel
    title: str
    content: str
    source: str = "oi_wiki"
    rewrite_version: int = 1


class CodeTemplateRead(BaseSchema):
    id: UUID
    knowledge_id: UUID
    language: str
    template_code: str
    explanation: str | None
