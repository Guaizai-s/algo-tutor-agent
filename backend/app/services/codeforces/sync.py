"""Codeforces 数据同步服务 (Task 8.2 / 8.3 / 8.4)。

三个核心同步流程：
- sync_problemset: problemset.problems 全量同步（每日）
- sync_user_status: user.status 增量同步（每用户每 5 分钟）
- sync_user_rating: user.rating 同步（每日）

设计要点：
- 所有写入幂等：基于 CF submission_id / (contest_id, index) / (user_id, contest_id) 唯一约束
- problemset 同步使用批量 upsert，不逐条 commit
- user.status 增量同步优先用 last_submission_id 作为游标，避免时间戳漏记录
- 单个用户失败不影响其他用户
- OK submission 正确触发 UserProblemAC 写入 + 掌握度重算
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.codeforces import CodeforcesAccount, RatingHistory, Submission
from app.models.learning import UserProblemAC
from app.models.problem import Problem, ProblemSource, ProblemStatus
from app.services.codeforces.client import CodeforcesClient, get_codeforces_client
from app.services.progress import recompute_mastery

logger = logging.getLogger(__name__)

# 单次 upsert 批量大小，避免单条 SQL 过大
UPSERT_BATCH_SIZE = 500


async def sync_problemset(
    db: AsyncSession,
    client: CodeforcesClient | None = None,
) -> dict[str, int]:
    """全量同步 CF problemset.problems。

    - 批量 upsert CF 题目到 problems 表
    - 不删除平台自建题目
    - 不保存题面正文
    - 幂等：基于 (cf_contest_id, cf_index) 唯一约束

    Returns:
        {"synced": 新增+更新数, "total": CF 返回题目总数}
    """
    client = client or get_codeforces_client()
    result = await client.problemset_problems()
    problems = result.get("problems", [])

    synced = 0
    for i in range(0, len(problems), UPSERT_BATCH_SIZE):
        batch = problems[i : i + UPSERT_BATCH_SIZE]
        rows = [_problem_to_row(p) for p in batch]
        # PostgreSQL INSERT ... ON CONFLICT DO UPDATE
        stmt = pg_insert(Problem).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_problems_cf_contest_index",
            set_={
                "title": stmt.excluded.title,
                "cf_tags": stmt.excluded.cf_tags,
                "cf_rating": stmt.excluded.cf_rating,
                "external_url": stmt.excluded.external_url,
            },
        )
        await db.execute(stmt)
        synced += len(batch)

    await db.flush()
    logger.info("CF problemset sync: synced=%d / total=%d", synced, len(problems))
    return {"synced": synced, "total": len(problems)}


def _problem_to_row(p: dict) -> dict:
    """将 CF problemset.problems 的单条题目转为 Problem upsert 行。

    保留字段：title, slug, description(占位), source=codeforces,
    cf_contest_id, cf_index, external_url, cf_tags, cf_rating, status=published
    """
    contest_id = p["contestId"]
    index = p["index"]
    name = p["name"]
    # slug 用 cf-{contest_id}-{index} 保证全局唯一
    slug = f"cf-{contest_id}-{index}"
    rating = p.get("rating")
    tags = p.get("tags", [])
    url = f"https://codeforces.com/problemset/problem/{contest_id}/{index}"

    return {
        "title": name,
        "slug": slug,
        # CF 题目不存题面正文，用 URL 替代
        "description": f"Codeforces problem {contest_id}{index}. See {url}",
        "source": ProblemSource.CODEFORCES,
        "cf_contest_id": contest_id,
        "cf_index": index,
        "external_url": url,
        "cf_tags": tags,
        "cf_rating": float(rating) if rating is not None else None,
        "status": ProblemStatus.PUBLISHED,
    }


# CF API user.status 分页参数
# 每页拉取数量：1000（CF API 推荐值，平衡请求次数与单次响应大小）
USER_STATUS_PAGE_SIZE = 1000
# 首次同步的最大页数上限（避免极端用户拖垮 Celery 任务超时）
# 1000 页 × 1000 条/页 = 100 万条，覆盖任何正常用户的历史
USER_STATUS_INITIAL_MAX_PAGES = 1000
# 增量同步的最大页数上限（5 分钟间隔内新提交不会超过几页）
USER_STATUS_INCREMENTAL_MAX_PAGES = 10


async def sync_user_status(
    db: AsyncSession,
    account: CodeforcesAccount,
    client: CodeforcesClient | None = None,
) -> dict[str, int | str | None]:
    """增量同步用户 CF user.status，使用真正的分页拉取。

    拉取策略（基于 CF API 的 from + count 参数）：
    - 首次同步（last_submission_id is None）：从 from=1 开始循环拉取每页 1000 条，
      直到返回 < count 条（即拉完全部历史）或达到 max_pages 上限。
    - 增量同步：从 from=1 开始循环拉取每页 1000 条，遇到 id <= 游标 即停止
      （已到上次同步点）；若一直没有遇到游标则继续拉取直到 max_pages 上限。

    游标推进规则（关键：防止数据丢失）：
    - 只有 reached_cursor=True（真正拉到上次同步点）时才推进游标。
    - 若达到 max_pages 上限但 reached_cursor=False，说明新提交太多、本轮没拉完，
      此时**不推进游标**，下次同步从同一游标重新拉取（已写入的 submission 因幂等约束
      不会重复，未拉到的会被下次补上）。返回值标记 truncated=True 供监控告警。
    - 首次同步若达到 max_pages 上限，说明历史超过 100 万条，同样不推进游标，
      下次仍按首次同步处理。

    幂等保证：通过 (cf_submission_id, user_id) 唯一约束，重复同步不会产生重复记录。

    Args:
        db: 数据库会话
        account: CodeforcesAccount，使用其 handle 和 last_submission_id 游标
        client: 可选的 CF API 客户端（测试注入）

    Returns:
        成功：{"new_submissions", "new_ac", "pages_fetched", "reached_cursor", "truncated"}
        失败：{"new_submissions": 0, "new_ac": 0, "pages_fetched", "error": str}
        - truncated=True 表示因达到 max_pages 上限未拉完，游标未推进，需下次继续
    """
    client = client or get_codeforces_client()

    is_initial = account.last_submission_id is None
    last_id = account.last_submission_id or 0
    max_pages = USER_STATUS_INITIAL_MAX_PAGES if is_initial else USER_STATUS_INCREMENTAL_MAX_PAGES

    # 收集所有新提交（跨页合并后再统一处理）
    all_new_subs: list[dict] = []
    pages_fetched = 0
    reached_cursor = False
    truncated = False  # 达到 max_pages 上限但未到达游标

    try:
        for page_idx in range(max_pages):
            from_ = page_idx * USER_STATUS_PAGE_SIZE + 1
            page = await client.user_status(
                account.handle,
                from_=from_,
                count=USER_STATUS_PAGE_SIZE,
            )
            pages_fetched += 1

            if not page:
                # 空页：已拉完所有数据。
                # 对增量同步，既然拉到空页，说明已遍历到历史最深处，自然已"到达游标"。
                reached_cursor = True
                break

            # 检查本页是否有游标之前（已同步）的 submission
            new_in_page = [s for s in page if s["id"] > last_id]
            all_new_subs.extend(new_in_page)

            # 增量同步：本页包含游标之前的 submission 说明已到达上次同步点
            if not is_initial and len(new_in_page) < len(page):
                reached_cursor = True
                break

            # 本页不足 count 条，说明是最后一页（已拉完所有数据）
            if len(page) < USER_STATUS_PAGE_SIZE:
                # 增量同步拉到最后一页：与空页同理，认为已到达游标
                reached_cursor = True
                break

            # 循环到达最后一页（range 已结束）：标记 truncated
            if page_idx == max_pages - 1:
                truncated = True
                logger.warning(
                    "CF user.status sync for handle=%s reached max_pages=%d without "
                    "reaching cursor; cursor NOT advanced, will continue next run",
                    account.handle,
                    max_pages,
                )
    except Exception as exc:
        logger.error("CF user.status sync failed for handle=%s: %s", account.handle, exc)
        return {
            "new_submissions": 0,
            "new_ac": 0,
            "pages_fetched": pages_fetched,
            "error": str(exc),
        }

    if not all_new_subs:
        logger.debug(
            "CF user.status sync: no new submissions for handle=%s (pages=%d)",
            account.handle,
            pages_fetched,
        )
        account.last_status_synced_at = datetime.now(tz=UTC)
        await db.flush()
        return {
            "new_submissions": 0,
            "new_ac": 0,
            "pages_fetched": pages_fetched,
            "reached_cursor": reached_cursor,
            "truncated": truncated,
        }

    # 按 submission id 升序处理，便于更新游标
    all_new_subs.sort(key=lambda s: s["id"])

    # 批量预解析 problem_id：一次查询所有 (contest_id, index) 对
    problem_keys: set[tuple[int | None, str | None]] = {
        (s.get("problem", {}).get("contestId"), s.get("problem", {}).get("index")) for s in all_new_subs
    }
    problem_id_map = await _batch_resolve_problem_ids(db, problem_keys)

    # 收集受影响的知识点（用于最后重算 mastery）
    affected_problem_ids: set[UUID] = set()
    new_ac_count = 0
    new_sub_count = 0
    max_sub_id = last_id

    for sub in all_new_subs:
        sub_id = sub["id"]
        if sub_id <= last_id:
            continue
        max_sub_id = max(max_sub_id, sub_id)

        problem_info = sub.get("problem", {})
        contest_id = problem_info.get("contestId")
        index = problem_info.get("index")
        verdict = sub.get("verdict", "")
        problem_id = problem_id_map.get((contest_id, index))

        # 构造 submission row
        row = {
            "cf_submission_id": sub_id,
            "user_id": account.user_id,
            "problem_id": problem_id,
            "contest_id": contest_id or 0,
            "problem_index": index or "",
            "handle_snapshot": account.handle,
            "verdict": verdict,
            "programming_language": sub.get("programmingLanguage", ""),
            "submitted_at": datetime.fromtimestamp(sub["creationTimeSeconds"], tz=UTC),
            "time_consumed_ms": sub.get("timeConsumedMillis", 0),
            "memory_consumed_bytes": sub.get("memoryConsumedBytes", 0),
            "passed_test_count": sub.get("passedTestCount", 0),
        }

        # 幂等插入：若 (cf_submission_id, user_id) 已存在则跳过
        stmt = pg_insert(Submission).values(row).on_conflict_do_nothing(constraint="uq_submission_cf_id_user")
        result = await db.execute(stmt)
        if result.rowcount > 0:
            new_sub_count += 1
            if problem_id is not None:
                affected_problem_ids.add(problem_id)

            # verdict=OK 写入 UserProblemAC（幂等）
            if verdict == "OK" and problem_id is not None:
                ac_stmt = (
                    pg_insert(UserProblemAC)
                    .values(
                        user_id=account.user_id,
                        problem_id=problem_id,
                    )
                    .on_conflict_do_nothing(constraint="uq_user_problem")
                )
                ac_result = await db.execute(ac_stmt)
                if ac_result.rowcount > 0:
                    new_ac_count += 1

    # 更新游标：只有真正拉完所有数据（reached_cursor=True）时才推进，防止数据丢失
    # truncated=True 时游标保持不变，下次同步从同一游标继续（幂等约束保证不重复）
    if reached_cursor and max_sub_id > last_id:
        account.last_submission_id = max_sub_id
    elif truncated:
        # 不推进游标；已写入的 submission 下次会被幂等跳过，未拉到的会被补上
        pass
    else:
        # reached_cursor=False 且未 truncated：理论上不应发生（break 前必有 reached_cursor
        # 或 truncated），防御性不推进并记录警告
        logger.warning(
            "CF user.status sync for handle=%s: reached_cursor=False and truncated=False, "
            "cursor NOT advanced (defensive)",
            account.handle,
        )

    account.last_status_synced_at = datetime.now(tz=UTC)
    await db.flush()

    # 为受影响的知识点重算 mastery（通过 problem_id 找到关联的知识点）
    if affected_problem_ids:
        await _recompute_mastery_for_problems(db, account.user_id, affected_problem_ids)

    logger.info(
        "CF user.status sync for handle=%s (initial=%s, pages=%d, reached_cursor=%s, truncated=%s): "
        "new_submissions=%d, new_ac=%d, cursor_advanced=%s",
        account.handle,
        is_initial,
        pages_fetched,
        reached_cursor,
        truncated,
        new_sub_count,
        new_ac_count,
        account.last_submission_id != last_id,
    )
    return {
        "new_submissions": new_sub_count,
        "new_ac": new_ac_count,
        "pages_fetched": pages_fetched,
        "reached_cursor": reached_cursor,
        "truncated": truncated,
    }


async def _batch_resolve_problem_ids(
    db: AsyncSession,
    keys: set[tuple[int | None, str | None]],
) -> dict[tuple[int | None, str | None], UUID]:
    """批量查询 (cf_contest_id, cf_index) -> Problem.id 映射。

    避免在分页同步中对每条 submission 单独查询 Problem 表。
    None 键自动跳过。
    """
    valid_keys = [(c, i) for (c, i) in keys if c is not None and i is not None]
    if not valid_keys:
        return {}
    # 构造 OR 条件查询
    from sqlalchemy import or_

    conditions = [(Problem.cf_contest_id == c) & (Problem.cf_index == i) for (c, i) in valid_keys]
    rows = (await db.execute(select(Problem.id, Problem.cf_contest_id, Problem.cf_index).where(or_(*conditions)))).all()
    return {(row.cf_contest_id, row.cf_index): row.id for row in rows}


async def _resolve_problem_id(db: AsyncSession, contest_id: int | None, index: str | None) -> UUID | None:
    """根据 (cf_contest_id, cf_index) 查找已同步的 Problem（单条，保留给 sync_single_user_status_task 用）。

    若 CF 题目尚未同步到 Problem 表，返回 None。
    """
    if contest_id is None or index is None:
        return None
    row = (
        await db.execute(
            select(Problem.id).where(
                Problem.cf_contest_id == contest_id,
                Problem.cf_index == index,
            )
        )
    ).scalar_one_or_none()
    return row


async def _recompute_mastery_for_problems(db: AsyncSession, user_id: UUID, problem_ids: set[UUID]) -> None:
    """为受影响的知识点重算 mastery。

    给定一批 problem_id，找到它们关联的知识点，然后重算这些知识点的 mastery。
    """
    if not problem_ids:
        return
    from app.models.problem import ProblemKnowledgePoint

    kp_ids = (
        (
            await db.execute(
                select(ProblemKnowledgePoint.knowledge_id).where(ProblemKnowledgePoint.problem_id.in_(problem_ids))
            )
        )
        .scalars()
        .all()
    )
    kp_ids = list(set(kp_ids))
    if not kp_ids:
        return
    # 对每个受影响的知识点单独重算（recompute_mastery 接受单个 knowledge_id）
    for kid in kp_ids:
        try:
            await recompute_mastery(db, user_id, kid)
        except ValueError:
            # 知识点可能在并发中被删除，忽略
            logger.warning("recompute_mastery for knowledge %s failed: not found", kid)


async def sync_user_rating(
    db: AsyncSession,
    account: CodeforcesAccount,
    client: CodeforcesClient | None = None,
) -> dict[str, int]:
    """同步用户 CF user.rating 历史。

    - 幂等写入 RatingHistory（基于 (user_id, contest_id) 唯一约束）
    - 更新 CodeforcesAccount.current_rating
    - 能正确处理从未参加 rated contest（空历史）

    Returns:
        {"new_ratings": 新增 RatingHistory 数, "current_rating": 最新 rating 或 None}
    """
    client = client or get_codeforces_client()

    try:
        ratings_data = await client.user_rating(account.handle)
    except Exception as exc:
        logger.error("CF user.rating sync failed for handle=%s: %s", account.handle, exc)
        return {"new_ratings": 0, "current_rating": account.current_rating, "error": str(exc)}

    new_count = 0
    current_rating: int | None = None

    for r in ratings_data:
        contest_id = r["contestId"]
        row = {
            "user_id": account.user_id,
            "handle": account.handle,
            "contest_id": contest_id,
            "contest_name": r.get("contestName", ""),
            "rank": r.get("rank", 0),
            "old_rating": r.get("oldRating", 0),
            "new_rating": r.get("newRating", 0),
            "rated_at": datetime.fromtimestamp(r["ratingUpdateTimeSeconds"], tz=UTC),
        }
        stmt = pg_insert(RatingHistory).values(row).on_conflict_do_nothing(constraint="uq_rating_history_user_contest")
        result = await db.execute(stmt)
        if result.rowcount > 0:
            new_count += 1
        # 最新 rating 是最后一条
        current_rating = r.get("newRating")

    account.current_rating = current_rating
    account.last_rating_synced_at = datetime.now(tz=UTC)
    await db.flush()

    logger.info(
        "CF user.rating sync for handle=%s: new_ratings=%d, current_rating=%s",
        account.handle,
        new_count,
        current_rating,
    )
    return {"new_ratings": new_count, "current_rating": current_rating}


async def sync_all_users_status(
    db: AsyncSession,
    client: CodeforcesClient | None = None,
) -> list[dict]:
    """同步所有已绑定 CF 账号的 user.status。

    单个账号失败不影响其他账号：使用 SAVEPOINT 隔离每个账号的写入，
    失败时回滚到 savepoint，继续处理下一个账号。

    状态判定：
    - sync_user_status 内部捕获 API 异常后返回带 "error" 字段的字典，视为失败
    - 抛出异常（如数据库错误）也视为失败

    Returns:
        每个账号一个 dict，包含 handle / status / new_submissions / new_ac
    """
    accounts = (await db.execute(select(CodeforcesAccount))).scalars().all()

    results = []
    for account in accounts:
        try:
            # 使用 savepoint 隔离：失败时只回滚本账号的写入
            async with db.begin_nested():
                result = await sync_user_status(db, account, client)
                # sync_user_status 内部捕获 API 异常后返回 error 字典
                if "error" in result:
                    # 抛出异常触发 savepoint 回滚，丢弃本账号的未提交写入
                    raise RuntimeError(str(result["error"]))
            # savepoint 正常提交后才标记成功
            result["handle"] = account.handle
            result["status"] = "ok"
        except Exception as exc:
            logger.error("CF user.status sync failed for handle=%s: %s", account.handle, exc)
            result = {
                "handle": account.handle,
                "status": "error",
                "error": str(exc),
                "new_submissions": 0,
                "new_ac": 0,
            }
        results.append(result)
    return results


async def sync_all_users_rating(
    db: AsyncSession,
    client: CodeforcesClient | None = None,
) -> list[dict]:
    """同步所有已绑定 CF 账号的 user.rating。

    单个账号失败不影响其他账号：使用 SAVEPOINT 隔离。
    """
    accounts = (await db.execute(select(CodeforcesAccount))).scalars().all()

    results = []
    for account in accounts:
        try:
            async with db.begin_nested():
                result = await sync_user_rating(db, account, client)
                if "error" in result:
                    raise RuntimeError(str(result["error"]))
            result["handle"] = account.handle
            result["status"] = "ok"
        except Exception as exc:
            logger.error("CF user.rating sync failed for handle=%s: %s", account.handle, exc)
            result = {
                "handle": account.handle,
                "status": "error",
                "error": str(exc),
                "new_ratings": 0,
                "current_rating": account.current_rating,
            }
        results.append(result)
    return results
