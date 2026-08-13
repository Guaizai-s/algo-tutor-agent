from __future__ import annotations

from dataclasses import dataclass

import pytest

from scripts.repair_alembic_version import choose_canonical_revision


@dataclass
class Revision:
    revision: str
    down_revision: str | None


class Script:
    def __init__(self, chain: dict[str, str | None]) -> None:
        self.chain = chain

    def get_revision(self, revision: str) -> Revision:
        return Revision(revision, self.chain[revision])


def test_choose_canonical_revision_keeps_descendant() -> None:
    script = Script({"head": "middle", "middle": "base", "base": None})
    assert choose_canonical_revision(script, {"base", "middle"}) == "middle"


def test_choose_canonical_revision_rejects_incomparable_rows() -> None:
    script = Script({"left": "base", "right": "base", "base": None})
    with pytest.raises(RuntimeError, match="cannot safely choose"):
        choose_canonical_revision(script, {"left", "right"})
