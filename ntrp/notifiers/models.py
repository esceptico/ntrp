import json
from dataclasses import dataclass
from datetime import datetime


@dataclass
class NotifierConfig:
    name: str
    type: str
    config: dict
    created_at: datetime

    def __post_init__(self):
        if isinstance(self.config, str):
            self.config = json.loads(self.config)
        if isinstance(self.created_at, str):
            self.created_at = datetime.fromisoformat(self.created_at)
