from pydantic import BaseModel, ConfigDict


class _FrozenEvent(BaseModel):
    model_config = ConfigDict(frozen=True)


class FactCreated(_FrozenEvent):
    fact_id: int
    text: str


class FactUpdated(_FrozenEvent):
    fact_id: int
    text: str


class FactDeleted(_FrozenEvent):
    fact_id: int


class MemoryCleared(_FrozenEvent):
    pass
