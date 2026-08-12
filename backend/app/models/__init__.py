from app.models.base import TimestampMixin, UUIDMixin
from app.models.codeforces import CodeforcesAccount, RatingHistory, Submission
from app.models.discussion import Discussion, DiscussionCategory, DiscussionComment
from app.models.knowledge import (
    CodeTemplate,
    KnowledgePoint,
    KnowledgePointDifficulty,
    KnowledgePrerequisite,
    Lecture,
    LectureLevel,
)
from app.models.learning import (
    CONSECUTIVE_WA_THRESHOLD,
    MASTERY_THRESHOLD,
    WEAK_MASTERY_THRESHOLD,
    CheckIn,
    DailyTask,
    DailyTaskItem,
    DailyTaskItemStatus,
    DailyTaskItemType,
    LearningPath,
    LearningPathItem,
    LearningProfile,
    PathItemKind,
    PathItemStatus,
    ReviewRecord,
    ReviewStage,
    UserKnowledgeState,
    UserProblemAC,
)
from app.models.notification import Notification, NotificationType
from app.models.problem import (
    Problem,
    ProblemDifficulty,
    ProblemKnowledgePoint,
    ProblemStatus,
    ProblemVariant,
)
from app.models.user import TargetMedal, User, UserRole
from app.models.wrongbook import WrongBookEntry

__all__ = [
    "TimestampMixin",
    "UUIDMixin",
    "KnowledgePoint",
    "KnowledgePointDifficulty",
    "KnowledgePrerequisite",
    "Lecture",
    "LectureLevel",
    "CodeTemplate",
    "Problem",
    "ProblemDifficulty",
    "ProblemStatus",
    "ProblemKnowledgePoint",
    "ProblemVariant",
    # Task 10 学习路径与推送引擎
    "UserKnowledgeState",
    "UserProblemAC",
    "LearningProfile",
    "LearningPath",
    "LearningPathItem",
    "PathItemKind",
    "PathItemStatus",
    "DailyTask",
    "DailyTaskItem",
    "DailyTaskItemStatus",
    "DailyTaskItemType",
    "MASTERY_THRESHOLD",
    "WEAK_MASTERY_THRESHOLD",
    "CONSECUTIVE_WA_THRESHOLD",
    # Task 15 讨论区
    "Discussion",
    "DiscussionCategory",
    "DiscussionComment",
    # Task 2 用户认证
    "User",
    "UserRole",
    "TargetMedal",
    # Task 12 错题本
    "WrongBookEntry",
    # Task 12 智能推送引擎
    "Notification",
    "NotificationType",
    # Task 13 艾宾浩斯复习
    "CheckIn",
    "ReviewRecord",
    "ReviewStage",
    # Task 8 Codeforces
    "CodeforcesAccount",
    "Submission",
    "RatingHistory",
]
