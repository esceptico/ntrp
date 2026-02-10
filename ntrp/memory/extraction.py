from pydantic import BaseModel

from ntrp.constants import EXTRACTION_TEMPERATURE
from ntrp.llm import acompletion
from ntrp.logging import get_logger
from ntrp.memory.models import ExtractedEntity, ExtractionResult
from ntrp.memory.prompts import EXTRACTION_PROMPT

_logger = get_logger(__name__)


class EntitySchema(BaseModel):
    name: str


class ExtractionSchema(BaseModel):
    entities: list[EntitySchema] = []


class Extractor:
    def __init__(self, model: str):
        self.model = model

    async def extract(self, text: str) -> ExtractionResult:
        try:
            response = await acompletion(
                model=self.model,
                messages=[{"role": "user", "content": EXTRACTION_PROMPT.format(text=text)}],
                response_format=ExtractionSchema,
                temperature=EXTRACTION_TEMPERATURE,
            )

            if (content := response.choices[0].message.content) is None:
                return ExtractionResult()

            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            parsed = ExtractionSchema.model_validate_json(content)
            return ExtractionResult(
                entities=[ExtractedEntity(name=e.name) for e in parsed.entities],
            )
        except Exception:
            _logger.warning("Extraction failed", exc_info=True)
            return ExtractionResult()
