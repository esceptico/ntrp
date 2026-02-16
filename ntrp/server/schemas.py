from pydantic import BaseModel, Field


# --- Chat / run ---


class ChatRequest(BaseModel):
    message: str
    skip_approvals: bool = False


class ToolResultRequest(BaseModel):
    run_id: str
    tool_id: str
    result: str
    approved: bool = True


class CancelRequest(BaseModel):
    run_id: str


class ChoiceResultRequest(BaseModel):
    run_id: str
    tool_id: str
    selected: list[str]


# --- Session / config ---


class SessionResponse(BaseModel):
    session_id: str
    sources: list[str]
    source_errors: dict[str, str]


class SourceToggles(BaseModel):
    gmail: bool | None = None
    calendar: bool | None = None
    memory: bool | None = None


class UpdateConfigRequest(BaseModel):
    chat_model: str | None = None
    explore_model: str | None = None
    memory_model: str | None = None
    max_depth: int | None = None
    vault_path: str | None = None
    browser: str | None = None
    browser_days: int | None = None
    sources: SourceToggles | None = None


class UpdateEmbeddingRequest(BaseModel):
    embedding_model: str


class UpdateDirectivesRequest(BaseModel):
    content: str


# --- Memory data ---


class UpdateFactRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)


class UpdateObservationRequest(BaseModel):
    summary: str = Field(..., min_length=1, max_length=10000)


# --- Schedule / notifiers ---


class UpdateScheduleRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class SetNotifiersRequest(BaseModel):
    notifiers: list[str]


class CreateNotifierRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: str
    config: dict


class UpdateNotifierRequest(BaseModel):
    config: dict
    name: str | None = None


# --- Skills ---


class InstallRequest(BaseModel):
    source: str = Field(..., min_length=5, description="GitHub path: owner/repo/path/to/skill")
