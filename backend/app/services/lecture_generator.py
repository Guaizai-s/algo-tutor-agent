"""AI 讲义改写服务（Phase 1）。

将 OI-Wiki + 左程云原始讲义用 OpenAI 改写为统一风格、带有"算法教练"品牌调性的独家讲义。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.knowledge import KnowledgePoint, Lecture, LectureSource

logger = logging.getLogger(__name__)

LECTURE_REWRITE_SYSTEM_PROMPT = """你是"算法教练"平台的讲义编写专家，负责将零散的算法学习资料改写为统一风格、高质量的教学讲义。

你的讲义读者是正在学习数据结构与算法的学生，他们需要清晰、鼓励式、实战导向的内容。

## 写作规范

### 结构要求（按顺序）
1. **概念引入**：用一两句话引出这个知识点，让读者知道要学什么、有什么用
2. **核心原理**：清晰解释算法/数据结构的核心思想，配合伪代码或图解描述
3. **代码模板**：给出 C++ 实现模板代码，带关键注释
4. **复杂度分析**：明确时间复杂度和空间复杂度，说明变量含义
5. **常见误区**：列出 1-3 个新手容易犯的错误及避坑方法
6. **练习建议**：建议读者练习哪些类型的题目来巩固

### 风格要求
- 口语化但不失严谨，像一位耐心的教练在和你对话
- 多用"你"拉近距离，例如"你可能会有疑问..."、"我们来看一个例子"
- 鼓励式语气："别担心，这个技巧多练几次就能掌握"
- 数学公式使用 $...$ 或 $$...$$ 包裹

### 深度控制
- 根据知识点本身的内容量和难度自行把握讲解深度
- 简单知识点（如栈、队列）精炼在 400-600 字
- 中等知识点（如二分查找、前缀和）展开到 600-1000 字
- 复杂知识点（如线段树、DP）可到 1000-2000 字

### 内容约束
- 严格基于提供的原始资料，不编造算法细节
- 保留原始资料中的技术准确性
- 如果原始资料中有代码示例，优先使用 C++ 版本
- 输出纯 Markdown 格式，不要用 ```markdown``` 包裹

## 格式示例

好的讲义格式如下：

## 概念引入
<内容>

## 核心原理
<内容，可含伪代码或图解描述>

## 代码模板
```cpp
// C++ 实现
```

## 复杂度分析
- 时间复杂度：...
- 空间复杂度：...

## 常见误区
1. **误区一**：...（避坑：...）
2. **误区二**：...

## 练习建议
- ...
"""


def _build_user_prompt(kp: KnowledgePoint, sources: list[Lecture]) -> str:
    """构建改写 prompt 的 user 部分。"""
    parts = [
        f"请将以下关于「{kp.name}」的原始学习资料改写为统一的算法教练讲义。",
        "",
        f"知识点难度：{kp.difficulty.value}",
    ]
    if kp.description:
        parts.append(f"知识点简介：{kp.description}")

    for i, lec in enumerate(sources, 1):
        # 截断过长内容，避免超出 token 限制
        content = lec.content
        if len(content) > 6000:
            content = content[:6000] + "\n\n...(内容过长，已截断)"
        parts.append(f"\n--- 原始资料 {i}：{lec.title} ---\n{content}")

    return "\n".join(parts)


def _compute_prompt_hash(prompt: str) -> str:
    """计算 prompt 的 SHA256 哈希，用于判断是否需要重新生成。"""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]


async def generate_rewritten_lecture(
    kp: KnowledgePoint,
    sources: list[Lecture],
) -> str:
    """用 OpenAI 改写讲义，返回 Markdown 格式的讲义内容。

    Args:
        kp: 目标知识点
        sources: 该知识点的所有原始讲义（OI-Wiki + 左程云）

    Returns:
        改写后的 Markdown 讲义内容
    """
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY or "missing",
        base_url=settings.OPENAI_BASE_URL,
        timeout=settings.OPENAI_REQUEST_TIMEOUT_SEC,
    )

    user_prompt = _build_user_prompt(kp, sources)

    try:
        resp = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": LECTURE_REWRITE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
            max_tokens=4096,
            extra_body={"thinking": {"type": "disabled"}},
        )
        content = resp.choices[0].message.content or ""
        return content.strip()
    except Exception:
        logger.exception("Failed to generate rewritten lecture for kp=%s", kp.slug)
        raise


async def batch_rewrite_all(
    db: AsyncSession,
    kp_ids: list[UUID] | None = None,
    force: bool = False,
) -> int:
    """批量改写知识点的讲义。

    Args:
        db: 数据库会话
        kp_ids: 要改写的知识点 ID 列表，None 表示全部
        force: 是否强制覆盖已有的 AI 改写讲义

    Returns:
        成功改写的知识点数量
    """
    # 只查询有原始讲义的知识点
    query = (
        select(KnowledgePoint)
        .distinct()
        .join(Lecture, Lecture.knowledge_id == KnowledgePoint.id)
        .where(Lecture.source.in_([LectureSource.OI_WIKI, LectureSource.ZUO_LECTURE]))
    )
    if kp_ids:
        query = query.where(KnowledgePoint.id.in_(kp_ids))
    kps = (await db.execute(query)).scalars().all()

    total = len(kps)
    print(f"共 {total} 个知识点待处理")
    rewritten_count = 0
    skipped_count = 0

    for i, kp in enumerate(kps, 1):
        # 获取该知识点的原始讲义（OI-Wiki + 左程云）
        sources_query = select(Lecture).where(
            Lecture.knowledge_id == kp.id,
            Lecture.source.in_([LectureSource.OI_WIKI, LectureSource.ZUO_LECTURE]),
        )
        sources = (await db.execute(sources_query)).scalars().all()

        if not sources:
            print(f"[{i}/{total}] SKIP {kp.name}: no source lectures")
            skipped_count += 1
            continue

        # 检查是否已有改写版本
        if not force:
            existing = (
                (
                    await db.execute(
                        select(Lecture).where(
                            Lecture.knowledge_id == kp.id,
                            Lecture.source == LectureSource.AI_REWRITTEN,
                        )
                    )
                )
                .scalars()
                .all()
            )
            if existing:
                print(f"[{i}/{total}] SKIP {kp.name}: already rewritten")
                skipped_count += 1
                continue

        # 生成改写讲义
        try:
            content = await generate_rewritten_lecture(kp, sources)
        except Exception:
            logger.exception("Failed to rewrite kp=%s, skipping", kp.slug)
            print(f"[{i}/{total}] FAIL {kp.name}")
            skipped_count += 1
            continue

        if not content:
            print(f"[{i}/{total}] SKIP {kp.name}: empty content")
            skipped_count += 1
            continue

        prompt_hash = _compute_prompt_hash(_build_user_prompt(kp, sources))

        # 写入 AI 改写讲义（取第一个原始讲义作为 source_lecture_id）
        rewritten = Lecture(
            knowledge_id=kp.id,
            level="standard",  # 遗留字段，AI 改写讲义统一用 standard
            title=f"{kp.name}（AI 精编）",
            content=content,
            source=LectureSource.AI_REWRITTEN,
            source_lecture_id=sources[0].id,
            rewrite_version=1,
            generation_prompt_hash=prompt_hash,
        )
        db.add(rewritten)
        await db.commit()
        rewritten_count += 1
        print(f"[{i}/{total}] OK  {kp.name} ({len(content)} chars)")

        # 每个知识点之间稍作延迟，避免 API 限流
        await asyncio.sleep(0.5)

    print(f"\n完成！改写 {rewritten_count}，跳过 {skipped_count}")
    return rewritten_count
