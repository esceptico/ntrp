"""Stage-4 lens — tool-and-retrieval slice (LENS_CONTRACTS §3.7, §3.8).

This package hosts the read-only retrieval-by-lens egress (`LensExpander`) and
the user-facing `lens` tool. Both are purely additive and consume what the
membership scorer / projector / lens service produce; neither scores membership,
writes claims, nor calls the strong model (LENS_CONTRACTS §3.7, §11.3).

The membership scorer, projector, write-back, and lens service themselves live
in `ntrp/memory/pipeline/` (built by their own components); this slice depends on
their frozen interfaces only, never on their internals.
"""

from ntrp.memory.lens.expand import LensExpander, LensExpansion
from ntrp.memory.lens.tool import (
    MEMORY_LENS_SERVICE,
    LensServiceProtocol,
    lens_tool,
)

__all__ = [
    "LensExpander",
    "LensExpansion",
    "MEMORY_LENS_SERVICE",
    "LensServiceProtocol",
    "lens_tool",
]
