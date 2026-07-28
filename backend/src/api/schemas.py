"""Pydantic 请求/响应 Schema"""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=50000, description="用户消息")
    user_id: str = Field(default="test", max_length=50)
    session_id: str | None = Field(default=None, max_length=128)


class UploadResponse(BaseModel):
    filename: str
    chunk_count: int


class KnowledgeFileResponse(BaseModel):
    id: int
    file_name: str
    file_type: str | None
    chunk_count: int
    status: str
    created_at: str | None


class TokenRecordResponse(BaseModel):
    id: int
    trace_id: str
    user_id: str
    model_name: str | None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_amount: float
    intent_type: str | None
    tool_called: int
    created_at: str | None


class TokenStatisticsResponse(BaseModel):
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    total_cost: float
    request_count: int
    tool_call_count: int
    avg_tokens_per_request: float


class TodayUsageResponse(BaseModel):
    today_tokens: int
    today_cost: float
    request_count: int


class ToolMetaResponse(BaseModel):
    name: str
    description: str
    permission: str
    category: str
    enabled: bool


class HealthComponent(BaseModel):
    chromadb: str
    postgresql: str
    llm: str


class HealthResponse(BaseModel):
    status: str
    components: HealthComponent | None = None
    version: str
    uptime: float | None = None
