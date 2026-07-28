"""应用配置 — pydantic-settings 从 .env 加载（55 配置项）"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置，自动从 .env 文件加载"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ==================== 项目路径 ====================
    PROJECT_ROOT: Path = Path(__file__).parent.parent.parent.resolve()
    DATA_DIR: Path = PROJECT_ROOT / "data"

    # ==================== AI 模型 ====================
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    MODEL_NAME: str = "qwen-plus"
    EMBEDDING_MODEL: str = "text-embedding-v3"

    # ==================== 应用 ====================
    APP_NAME: str = "Smart Assistant"
    APP_VERSION: str = "3.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"

    # ==================== 日志 ====================
    LOG_LEVEL: str = "INFO"

    # ==================== 知识库 ====================
    KNOWLEDGE_CHUNK_SIZE: int = 800
    KNOWLEDGE_OVERLAP: int = 150

    # ==================== 工具 ====================
    TOOL_TIMEOUT: int = 15
    TOOL_WRITE_TIMEOUT: int = 20
    MAX_RETRIES: int = 3

    # ==================== 数据库 ====================
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/assistant"
    DEAD_LETTER_DB_URL: str = "sqlite+aiosqlite:///data/dead_letter/dead_letter.db"

    # ==================== ChromaDB ====================
    CHROMA_URL: str = ""  # 空则用嵌入式 PersistentClient，填 http://localhost:8001 则用 HttpClient
    CHROMA_PERSIST_DIR: str = "data/chroma_db"  # 嵌入式模式使用

    # ==================== Redis ====================
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_PASSWORD: str = "smart123"

    # ==================== 邮件（SMTP） ====================
    SMTP_HOST: str = "smtp.163.com"
    SMTP_PORT: int = 465
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_SSL: bool = True
    SMTP_STARTTLS: bool = False

    # ==================== Token 配额 ====================
    TOKEN_DAILY_LIMIT: int = 500_000
    TOKEN_DAILY_COST_LIMIT: float = 10.0
    TOKEN_CACHE_READ_DISCOUNT: float = 0.1
    TOKEN_CACHE_WRITE_PREMIUM: float = 1.25
    TOKEN_DEFAULT_INPUT_PRICE: float = 0.0008
    TOKEN_DEFAULT_OUTPUT_PRICE: float = 0.002
    TOKEN_ALERT_THRESHOLD: float = 0.8
    TOKEN_ALERT_WEBHOOK: str = ""

    # ==================== Agent ====================
    AGENT_RECURSION_LIMIT: int = 10
    AGENT_MEMORY_MAX_MESSAGES: int = 20
    AGENT_SUMMARY_THRESHOLD: int = 12
    AGENT_MAX_DUPLICATE_CALLS: int = 3
    AGENT_CIRCUIT_BREAKER_THRESHOLD: int = 5
    AGENT_CIRCUIT_BREAKER_TIMEOUT: int = 60

    # ==================== 文件上传 ====================
    MAX_FILE_SIZE: int = 20_971_520  # 20MB
    ALLOWED_EXTENSIONS: str = "txt,pdf,doc,docx,xls,xlsx"

    # ==================== 检索 ====================
    HYBRID_SEARCH_ENABLED: bool = True
    VECTOR_CANDIDATE_MULTIPLIER: int = 3
    FTS_CANDIDATE_MULTIPLIER: int = 2
    RRF_CONSTANT_K: int = 30
    RE_RANKING_ENABLED: bool = True
    RE_RANK_THRESHOLD: int = 5
    MMR_ENABLED: bool = True
    MMR_LAMBDA: float = 0.7
    QUERY_REWRITING_ENABLED: bool = True
    DYNAMIC_THRESHOLD_ENABLED: bool = True
    SIMILARITY_THRESHOLD_BASE: float = 0.15

    # ==================== 记忆 ====================
    MEMORY_TTL_HOURS: int = 24
    MEMORY_SUMMARY_TTL_HOURS: int = 1

    # ==================== 限流 ====================
    RATE_LIMIT_PER_MINUTE: int = 30
    RATE_LIMIT_PER_DAY: int = 500

    # ==================== JWT ====================
    JWT_SECRET: str = "smart-assistant-jwt-secret-key-change-in-production"
    JWT_EXPIRE_MINUTES: int = 1440  # 24 小时

    # ==================== 数据清理 ====================
    AUDIT_LOG_RETENTION_DAYS: int = 90
    TOKEN_USAGE_RETENTION_DAYS: int = 365

    @property
    def chroma_path(self) -> str:
        """ChromaDB 持久化绝对路径"""
        if Path(self.CHROMA_PERSIST_DIR).is_absolute():
            return self.CHROMA_PERSIST_DIR
        return str(self.PROJECT_ROOT / self.CHROMA_PERSIST_DIR)

    @property
    def allowed_extensions_list(self) -> list[str]:
        """允许上传的文件扩展名列表"""
        return [ext.strip() for ext in self.ALLOWED_EXTENSIONS.split(",")]

    def validate_required(self) -> None:
        """启动时校验必填配置项"""
        from src.core.exceptions import ConfigError

        missing = []
        if not self.OPENAI_API_KEY:
            missing.append("OPENAI_API_KEY")
        if not self.SMTP_USERNAME:
            missing.append("SMTP_USERNAME")
        if missing:
            raise ConfigError(f"缺少必填配置项: {', '.join(missing)}，请检查 .env 文件")


# 全局单例
settings = Settings()
