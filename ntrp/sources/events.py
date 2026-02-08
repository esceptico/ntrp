from dataclasses import dataclass


@dataclass(frozen=True)
class SourceChanged:
    source_name: str
