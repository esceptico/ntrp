from ntrp.agent import CompletionResponse, Usage
from ntrp.llm.models import get_model


class UsageTracker:
    def __init__(self) -> None:
        self.usage = Usage()
        self.cost: float = 0.0

    async def track(self, response: CompletionResponse) -> None:
        self.usage += response.usage
        self.cost += get_model(response.model).pricing.cost(response.usage)
