"""Codeforces verdict groupings shared by synchronization and learning features."""

# Final verdicts that represent an unsuccessful solution attempt and should be
# available in the user's wrongbook. Transient states such as TESTING/SKIPPED
# and system-side failures are intentionally excluded.
WRONGBOOK_VERDICTS = frozenset(
    {
        "WRONG_ANSWER",
        "PRESENTATION_ERROR",
        "TIME_LIMIT_EXCEEDED",
        "MEMORY_LIMIT_EXCEEDED",
        "IDLENESS_LIMIT_EXCEEDED",
        "RUNTIME_ERROR",
        "COMPILATION_ERROR",
    }
)
