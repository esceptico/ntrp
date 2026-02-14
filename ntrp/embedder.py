from dataclasses import dataclass

import litellm
import numpy as np

from ntrp.constants import EMBEDDING_TEXT_LIMIT


@dataclass
class EmbeddingConfig:
    model: str
    dim: int


class Embedder:
    def __init__(self, config: EmbeddingConfig):
        self.config = config

    def _normalize(self, embeddings: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        return embeddings / np.where(norms == 0, 1, norms)

    def _parse_response(self, response) -> np.ndarray:
        sorted_data = sorted(response.data, key=lambda x: x["index"])
        embeddings = np.array([item["embedding"] for item in sorted_data])
        return self._normalize(embeddings)

    async def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.array([])
        truncated = [t[:EMBEDDING_TEXT_LIMIT] for t in texts]
        response = await litellm.aembedding(model=self.config.model, input=truncated)
        return self._parse_response(response)

    async def embed_one(self, text: str) -> np.ndarray:
        return (await self.embed([text]))[0]
