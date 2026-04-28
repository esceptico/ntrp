from typing import Annotated, Literal

from pydantic import BaseModel, Field

# --- Chat / run ---


class ImageBlock(BaseModel):
    media_type: str
    data: str


class ChatRequest(BaseModel):
    message: str = Field("", max_length=100_000)
    images: list[ImageBlock] = Field(default_factory=list)
    context: list[dict] = Field(default_factory=list)
    skip_approvals: bool = False
    session_id: str | None = None
    client_id: str | None = None


class ToolResultRequest(BaseModel):
    run_id: str
    tool_id: str
    result: str
    approved: bool = True


class CancelRequest(BaseModel):
    run_id: str


class BackgroundRequest(BaseModel):
    run_id: str


OutboxEventId = Annotated[int, Field(gt=0)]


class ReplayOutboxRequest(BaseModel):
    event_ids: list[OutboxEventId] = Field(..., min_length=1, max_length=100)


# --- Session / config ---


class SessionResponse(BaseModel):
    session_id: str
    integrations: list[str]
    integration_errors: dict[str, str]
    name: str | None = None


class CreateSessionRequest(BaseModel):
    name: str | None = None


class RenameSessionRequest(BaseModel):
    name: str


class CompactRequest(BaseModel):
    session_id: str | None = None


class ClearSessionRequest(BaseModel):
    session_id: str | None = None


class RevertRequest(BaseModel):
    session_id: str | None = None
    turns: int = Field(1, ge=1)


class IntegrationToggles(BaseModel):
    google: bool | None = None
    memory: bool | None = None
    dreams: bool | None = None


class UpdateConfigRequest(BaseModel):
    chat_model: str | None = None
    research_model: str | None = None
    memory_model: str | None = None
    max_depth: int | None = None
    compression_threshold: float | None = None
    max_messages: int | None = None
    compression_keep_ratio: float | None = None
    summary_max_tokens: int | None = None
    consolidation_interval: int | None = None
    vault_path: str | None = None
    web_search: Literal["auto", "exa", "ddgs", "none"] | None = None
    integrations: IntegrationToggles | None = None


class UpdateEmbeddingRequest(BaseModel):
    embedding_model: str


class UpdateDirectivesRequest(BaseModel):
    content: str


# --- Memory data ---


class UpdateFactRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)


class UpdateObservationRequest(BaseModel):
    summary: str = Field(..., min_length=1, max_length=10000)


# --- Automations / notifiers ---


class CreateAutomationRequest(BaseModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    model: str | None = None
    trigger_type: str | None = None
    at: str | None = None
    days: str | None = None
    every: str | None = None
    event_type: str | None = None
    lead_minutes: int | str | None = None
    writable: bool = False
    start: str | None = None
    end: str | None = None
    triggers: list[dict] | None = None
    cooldown_minutes: int | None = None


class UpdateAutomationRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    model: str | None = None
    trigger_type: str | None = None
    at: str | None = None
    days: str | None = None
    every: str | None = None
    event_type: str | None = None
    lead_minutes: int | str | None = None
    start: str | None = None
    end: str | None = None
    writable: bool | None = None
    enabled: bool | None = None
    triggers: list[dict] | None = None
    cooldown_minutes: int | None = None


class CreateNotifierRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: str
    config: dict


class UpdateNotifierRequest(BaseModel):
    config: dict
    name: str | None = None


# --- Skills ---


class ConnectProviderRequest(BaseModel):
    api_key: str = Field(..., min_length=1)
    chat_model: str | None = None


class ConnectServiceRequest(BaseModel):
    api_key: str = Field(..., min_length=1)


class AddCustomModelRequest(BaseModel):
    model_id: str = Field(..., min_length=1)
    base_url: str = Field(..., min_length=1)
    context_window: int = Field(..., gt=0)
    max_output_tokens: int = 8192
    api_key: str | None = None


# --- Skills ---


class InstallRequest(BaseModel):
    source: str = Field(..., min_length=5, description="GitHub path: owner/repo/path/to/skill")
