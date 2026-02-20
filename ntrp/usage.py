from dataclasses import dataclass


@dataclass(frozen=True)
class Pricing:
    price_in: float = 0
    price_out: float = 0
    price_cache_read: float = 0
    price_cache_write: float = 0


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost: float = 0.0

    def with_cost(self, pricing: Pricing) -> "Usage":
        return Usage(
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            cache_read_tokens=self.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens,
            cost=(
                self.prompt_tokens * pricing.price_in
                + self.completion_tokens * pricing.price_out
                + self.cache_read_tokens * pricing.price_cache_read
                + self.cache_write_tokens * pricing.price_cache_write
            )
            / 1_000_000,
        )

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
            cost=self.cost + other.cost,
        )

    def __iadd__(self, other: "Usage") -> "Usage":
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.cache_write_tokens += other.cache_write_tokens
        self.cost += other.cost
        return self

    def to_dict(self) -> dict:
        return {
            "prompt": self.prompt_tokens,
            "completion": self.completion_tokens,
            "total": self.prompt_tokens + self.completion_tokens,
            "cache_read": self.cache_read_tokens,
            "cache_write": self.cache_write_tokens,
            "cost": self.cost,
        }
