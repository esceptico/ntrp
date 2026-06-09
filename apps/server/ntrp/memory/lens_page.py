"""LensPage — synthesize a lens's member records into one editable markdown page.

The synthesis core of the deleted claim-pipeline `project.py`, stripped of the
anchor/citation/write-back/cache machinery (that fought the simpler records
model). ONE LLM call renders the members into a clean markdown directory. On a
blank/failed synthesis it degrades to a raw bulleted list of the members — never
a blank or hallucinated page. Membership is decided upstream (LensStore); this is
pure rendering.
"""

from ntrp.logging import get_logger
from ntrp.memory.models import Record
from ntrp.memory.prompts_project import PAGE_SYNTH_SYSTEM

_logger = get_logger(__name__)

DETAIL_LEVELS = ("gist", "structured", "dossier")


class LensPage:
    def __init__(self, llm, *, model: str | None, reasoning_effort: str | None = None) -> None:
        self._llm = llm
        self._model = model
        self._reasoning_effort = reasoning_effort

    async def synthesize(
        self, name: str, criterion: str, members: list[Record], *, detail: str = "structured"
    ) -> str:
        """Render `members` into a markdown page. Falls back to a raw bulleted
        list with no LLM, on failure, or on blank output."""
        if not members:
            return ""
        if self._llm is None or not self._model:
            return self._raw_list(members)
        level = detail if detail in DETAIL_LEVELS else "structured"
        listing = "\n".join(f"- {r.text}" for r in members)
        user = f"LENS: {name!r}\nCRITERION: {criterion!r}\nDETAIL: {level}\n\nMEMBER RECORDS:\n{listing}"
        try:
            resp = await self._llm.completion(
                messages=[
                    {"role": "system", "content": PAGE_SYNTH_SYSTEM},
                    {"role": "user", "content": user},
                ],
                model=self._model,
                reasoning_effort=self._reasoning_effort,
            )
        except Exception:
            _logger.warning("lens page synthesis failed; raw fallback", lens=name, exc_info=True)
            return self._raw_list(members)
        content = resp.choices[0].message.content if resp.choices else None
        text = (content or "").strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            if text.endswith("```"):
                text = text[: text.rfind("```")]
            text = text.strip()
        return text or self._raw_list(members)

    @staticmethod
    def _raw_list(members: list[Record]) -> str:
        return "\n".join(f"- {r.text}" for r in members)
