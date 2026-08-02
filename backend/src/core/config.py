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
    MODEL_NAME_LIGHT: str = "qwen-turbo"  # 轻量任务（分类/提取）用更快更便宜的模型
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

    # 工具限流（三层：单用户单工具 / 全局工具 / 单用户总 QPS，单位：次/分钟）
    TOOL_RATE_LIMIT_USER_TOOL: dict[str, int] = {
        "do_send_email": 3,
        "do_send_formatted_email": 3,
        "upload_knowledge": 5,
        "delete_knowledge": 10,
        "add_memo": 10,
        "update_memo": 10,
        "delete_memo": 10,
        "complete_memo": 10,
        "_default": 30,
    }
    TOOL_RATE_LIMIT_GLOBAL_TOOL: dict[str, int] = {
        "chroma_ops": 200,
        "smtp_ops": 30,
        "db_write": 500,
    }
    TOOL_RATE_LIMIT_USER_TOTAL: int = 60

    # 入参长度校验（字符数，0 或未配置则不限制）
    TOOL_INPUT_MAX_LENGTHS: dict[str, int] = {
        "add_memo.title": 50,
        "add_memo.content": 10000,
        "update_memo.title": 50,
        "update_memo.content": 10000,
        "upload_knowledge.file_path": 500,
        "do_send_email.body": 50000,
        "do_send_email.subject": 200,
        "do_send_formatted_email.content_items": 50000,
        "_default": 5000,
    }

    # 出参长度截断（字符数，0 则不截断）
    TOOL_OUTPUT_MAX_LENGTHS: dict[str, int] = {
        "get_document_content": 20000,
        "list_memos": 8000,
        "delete_memos_batch": 8000,
        "search_knowledge": 12000,
        "_default": 4000,
    }

    # 工具依赖健康检查间隔（秒）
    TOOL_HEALTH_CHECK_INTERVAL: int = 30

    # 审计日志异步刷入间隔（秒）
    TOOL_AUDIT_FLUSH_INTERVAL: int = 2

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
    AGENT_RECURSION_LIMIT: int = 15
    AGENT_MEMORY_MAX_MESSAGES: int = 20
    AGENT_SUMMARY_THRESHOLD: int = 12
    AGENT_MAX_DUPLICATE_CALLS: int = 5
    AGENT_CIRCUIT_BREAKER_THRESHOLD: int = 5
    AGENT_CIRCUIT_BREAKER_TIMEOUT: int = 60

    # ==================== 文件上传 ====================
    UPLOAD_DIR: str = "data/uploads"
    MAX_FILE_SIZE: int = 20_971_520  # 20MB
    ALLOWED_EXTENSIONS: str = "txt,pdf,doc,docx,xls,xlsx"

    @property
    def upload_dir(self) -> Path:
        """上传文件存储绝对路径（Docker 部署时应挂载为 volume）"""
        p = Path(self.UPLOAD_DIR)
        return p if p.is_absolute() else self.PROJECT_ROOT / p

    # ==================== 检索 ====================
    HYBRID_SEARCH_ENABLED: bool = True
    VECTOR_CANDIDATE_MULTIPLIER: int = 3
    FTS_CANDIDATE_MULTIPLIER: int = 2
    RRF_CONSTANT_K: int = 30
    RE_RANKING_ENABLED: bool = True
    RE_RANK_THRESHOLD: int = 10
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

    # ==================== API 全局限流 ====================
    # 格式: "路径前缀": 每分钟限制
    API_RATE_LIMITS: dict[str, int] = {
        "/api/v1/chat": 20,         # SSE 流式对话
        "/api/v1/auth/login": 10,   # 登录
        "/api/v1/auth/register": 5, # 注册
        "/api/v1/knowledge/upload": 10,  # 文件上传
        "/api/v1/memo": 60,         # 备忘录 CRUD
        "/api/v1/_default": 60,     # 兜底
    }
    API_RATE_LIMIT_IP_PER_MINUTE: int = 60     # 单 IP 全局限制
    API_RATE_LIMIT_USER_PER_MINUTE: int = 120  # 单用户全局限制

    # ==================== JWT ====================
    JWT_SECRET: str = "smart-assistant-jwt-secret-key-change-in-production"
    JWT_EXPIRE_MINUTES: int = 1440  # 24 小时

    # ==================== LangFuse（链路追踪） ====================
    LANGFUSE_HOST: str = ""
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""

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
