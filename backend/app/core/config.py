from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "算法教练平台"
    API_V1_STR: str = "/api/v1"

    POSTGRES_USER: str = "algo_tutor"
    POSTGRES_PASSWORD: str = "algo_tutor_secret"
    POSTGRES_DB: str = "algo_tutor"
    DATABASE_URL: str = "postgresql+asyncpg://algo_tutor:algo_tutor_secret@postgres:5432/algo_tutor"

    JWT_SECRET: str = "change-me-to-a-random-secret-key"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    REDIS_URL: str = "redis://redis:6379/0"

    OPENAI_API_KEY: str | None = None
    OPENAI_BASE_URL: str | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_REQUEST_TIMEOUT_SEC: float = 30.0

    # Agent
    AGENT_MAX_TOOL_ROUNDS: int = 5
    AGENT_REQUEST_TIMEOUT_SEC: float = 60.0

    # 代码执行沙箱
    SANDBOX_IMAGE: str = "algo-sandbox:latest"
    SANDBOX_NETWORK_DISABLED: bool = True
    SANDBOX_CPU_LIMIT: float = 1.0
    SANDBOX_MEMORY_LIMIT_MB: int = 256
    SANDBOX_PIDS_LIMIT: int = 64
    SANDBOX_DEFAULT_TIMEOUT_MS: int = 3000
    SANDBOX_MAX_TIMEOUT_MS: int = 5000
    SANDBOX_MAX_MEMORY_MB: int = 512
    SANDBOX_MAX_OUTPUT_BYTES: int = 16384
    SANDBOX_USER: str = "sandbox"

    # 检索 / RAG
    RAG_EMBEDDING_MODEL: str = "text-embedding-3-small"
    RAG_EMBEDDING_DIM: int = 1536
    RAG_DEFAULT_LIMIT: int = 5
    RAG_MAX_LIMIT: int = 10

    # Codeforces API (Task 8)
    CF_API_BASE_URL: str = "https://codeforces.com/api"
    # spec: 全局速率限制 >= 2 秒/次，跨 worker 通过 Redis 共享
    CF_API_MIN_INTERVAL_SEC: float = 2.0
    CF_API_CONNECT_TIMEOUT_SEC: float = 10.0
    CF_API_READ_TIMEOUT_SEC: float = 30.0
    CF_API_MAX_RETRIES: int = 5
    CF_API_BACKOFF_BASE_SEC: float = 1.0
    CF_API_BACKOFF_MAX_SEC: float = 60.0

    # 用户时区（用于 streak_days 自然日计算）
    # 数据库/容器运行在 UTC，但用户在 Asia/Shanghai
    USER_TIMEZONE: str = "Asia/Shanghai"

    # CORS（从 .env 读 list[str] 时需写成 JSON 数组：["http://..."]）
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
