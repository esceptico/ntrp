import os

import httpx

from ntrp.logging import get_logger

_logger = get_logger(__name__)

ZEROENTROPY_API_URL = "https://api.zeroentropy.dev/v1/models/rerank"
ZEROENTROPY_MODEL = "zerank-2"


async def rerank(
    query: str,
    documents: list[str],
    top_n: int | None = None,
) -> list[tuple[int, float]]:
    """Rerank documents using ZeroEntropy zerank-2.

    Returns [(original_index, relevance_score), ...] sorted by score desc.
    Returns empty list if API key not set or on failure (graceful fallback).
    """
    api_key = os.environ.get("ZEROENTROPY_API_KEY")
    if not api_key or not documents:
        return []

    body: dict = {
        "model": ZEROENTROPY_MODEL,
        "query": query,
        "documents": documents,
    }
    if top_n is not None:
        body["top_n"] = top_n

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                ZEROENTROPY_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()

        results = [
            (r["index"], r["relevance_score"])
            for r in data["results"]
        ]
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    except Exception as e:
        _logger.warning("reranker failed, falling back to base scoring", error=str(e))
        return []
