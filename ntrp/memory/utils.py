from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import numpy as np

type EmbedFn = Callable[[str], Awaitable[np.ndarray]]


def ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt
