"""On-demand synchronization of public Codeforces statements and samples.

The official Codeforces API exposes problem metadata but not statements or
sample tests.  Luogu mirrors the public statement in a JSON script embedded in
the page.  This service parses that stable data envelope and caches only public
content; hidden judge tests are never fetched or stored.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from typing import Any

import httpx

from app.core.config import settings
from app.models.problem import Problem, ProblemSource

logger = logging.getLogger(__name__)


class ProblemContentError(RuntimeError):
    """The public problem content could not be fetched or parsed."""


@dataclass(frozen=True)
class PublicProblemContent:
    description: str
    sample_input: str
    sample_output: str
    time_limit_ms: int | None = None
    memory_limit_kb: int | None = None


class _ContextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._capturing = False
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "script" and attributes.get("id") == "lentille-context":
            self._capturing = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._capturing:
            self._capturing = False

    def handle_data(self, data: str) -> None:
        if self._capturing:
            self._parts.append(data)

    @property
    def context(self) -> str:
        return "".join(self._parts).strip()


def _first_limit(value: Any) -> int | None:
    if isinstance(value, list) and value:
        value = value[0]
    if isinstance(value, (int, float)) and value > 0:
        return int(value)
    return None


def parse_luogu_problem_page(page: str) -> PublicProblemContent:
    parser = _ContextParser()
    parser.feed(page)
    if not parser.context:
        raise ProblemContentError("mirror response has no lentille-context")

    try:
        payload = json.loads(parser.context)
        problem = payload["data"]["problem"]
        content = problem["content"]
        samples = problem["samples"]
        first_sample = samples[0]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise ProblemContentError("mirror response has no usable public sample") from exc

    description = content.get("description")
    sample_input, sample_output = first_sample[0], first_sample[1]
    if not all(isinstance(value, str) and value.strip() for value in (description, sample_input, sample_output)):
        raise ProblemContentError("mirror returned incomplete statement or sample")

    limits = problem.get("limits") or {}
    sections = [description.strip()]
    for title, key in (("Input", "formatI"), ("Output", "formatO")):
        value = content.get(key)
        if isinstance(value, str) and value.strip():
            sections.append(f"{title}\n\n{value.strip()}")
    return PublicProblemContent(
        description="\n\n".join(sections),
        sample_input=sample_input.rstrip() + "\n",
        sample_output=sample_output.rstrip() + "\n",
        time_limit_ms=_first_limit(limits.get("time")),
        memory_limit_kb=_first_limit(limits.get("memory")),
    )


async def fetch_public_problem_content(
    contest_id: int,
    index: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> PublicProblemContent:
    url = f"{settings.CF_CONTENT_BASE_URL.rstrip('/')}/CF{contest_id}{index}"
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=settings.CF_CONTENT_CONNECT_TIMEOUT_SEC,
                read=settings.CF_CONTENT_READ_TIMEOUT_SEC,
                write=settings.CF_CONTENT_READ_TIMEOUT_SEC,
                pool=settings.CF_CONTENT_CONNECT_TIMEOUT_SEC,
            ),
            headers={"User-Agent": "algo-tutor-agent/1.0"},
            follow_redirects=True,
        )
    try:
        response = await client.get(url, params={"_contentOnly": "1"})
        response.raise_for_status()
        return parse_luogu_problem_page(response.text)
    except (httpx.HTTPError, ProblemContentError) as exc:
        raise ProblemContentError(f"failed to fetch CF{contest_id}{index}: {exc}") from exc
    finally:
        if owns_client:
            await client.aclose()


def content_sync_due(problem: Problem, *, now: datetime | None = None) -> bool:
    if problem.source != ProblemSource.CODEFORCES or problem.cf_contest_id is None or not problem.cf_index:
        return False
    if problem.sample_input and problem.sample_output:
        return False
    if problem.content_sync_failed_at is None:
        return True
    current = now or datetime.now(tz=UTC)
    retry_after = timedelta(minutes=settings.CF_CONTENT_RETRY_AFTER_MINUTES)
    return current - problem.content_sync_failed_at >= retry_after


async def sync_problem_content(problem: Problem, *, force: bool = False) -> bool:
    """Populate one ORM problem instance and return whether it was updated."""

    if not force and not content_sync_due(problem):
        return False
    if problem.source != ProblemSource.CODEFORCES or problem.cf_contest_id is None or not problem.cf_index:
        raise ProblemContentError("problem is not a valid Codeforces problem")

    now = datetime.now(tz=UTC)
    try:
        content = await fetch_public_problem_content(problem.cf_contest_id, problem.cf_index)
    except ProblemContentError:
        problem.content_sync_failed_at = now
        logger.warning("Public content sync failed for CF%s%s", problem.cf_contest_id, problem.cf_index)
        return False

    problem.description = content.description
    problem.sample_input = content.sample_input
    problem.sample_output = content.sample_output
    if content.time_limit_ms is not None:
        problem.time_limit_ms = content.time_limit_ms
    if content.memory_limit_kb is not None:
        problem.memory_limit_kb = content.memory_limit_kb
    problem.content_synced_at = now
    problem.content_sync_failed_at = None
    return True
