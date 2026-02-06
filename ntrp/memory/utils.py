from collections.abc import Awaitable, Callable

import numpy as np

type EmbedFn = Callable[[str], Awaitable[np.ndarray]]
