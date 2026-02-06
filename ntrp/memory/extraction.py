from ntrp.llm import acompletion
from pydantic import BaseModel

from ntrp.constants import EXTRACTION_TEMPERATURE
from ntrp.logging import get_logger
from ntrp.memory.models import ExtractedEntity, ExtractedEntityPair, ExtractionResult
from ntrp.memory.prompts import EXTRACTION_PROMPT

logger = get_logger(__name__)


class EntitySchema(BaseModel):
    name: str
    type: str


class EntityPairSchema(BaseModel):
    source: str
    target: str


class ExtractionSchema(BaseModel):
    entities: list[EntitySchema] = []
    entity_pairs: list[EntityPairSchema] = []


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

            parsed = ExtractionSchema.model_validate_json(content)
            return ExtractionResult(
                entities=[ExtractedEntity(name=e.name, entity_type=e.type) for e in parsed.entities],
                entity_pairs=[ExtractedEntityPair(source=p.source, target=p.target) for p in parsed.entity_pairs],
            )
        except Exception:
            logger.warning("Extraction failed", exc_info=True)
            return ExtractionResult()
