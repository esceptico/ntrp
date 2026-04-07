from collections.abc import Callable

from ntrp.config import Config

SOURCES: dict[str, Callable[[Config], object | None]] = {}
