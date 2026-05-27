import math

BASE_BY_PROVENANCE = {
    "recorded": 0.9,
    "user_authored": 0.95,
    "inferred": 0.75,
    "external": 0.6,
}


def _clamp(value: float, *, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def compute_confidence(
    *,
    provenance: str,
    parent_confidences: list[float],
    contradiction_count: int,
    age_days: float,
    last_used_days: float,
    helped: int,
    hurt: int,
    ignored: int,
) -> float:
    base = BASE_BY_PROVENANCE[provenance]
    provenance_component = base * (1.0 - 0.15 * math.tanh(contradiction_count))

    n = len(parent_confidences)
    w_evidence = sum(parent_confidences) / n if n else 1.0
    evidence = 0.5 + 0.5 * (1.0 - math.exp(-0.4 * n * w_evidence)) if n else 0.5

    decay = _clamp(
        0.7 * (1.0 + last_used_days) ** -0.5 + 0.3 * math.exp(-age_days / 100.0),
        lo=0.05,
        hi=1.0,
    )

    net_usage = helped - hurt - 0.3 * ignored
    ratio = net_usage / max(1, helped + hurt + ignored)
    usage = _clamp(0.85 + 0.15 * math.tanh(ratio), lo=0.5, hi=1.0)

    return provenance_component * evidence * decay * usage


def confidence_bucket(confidence: float) -> str:
    if confidence < 0.4:
        return "low"
    if confidence < 0.7:
        return "med"
    return "high"
