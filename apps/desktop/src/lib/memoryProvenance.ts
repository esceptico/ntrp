export interface FactSourceLike {
  source_type: string;
  source_ref: string | null;
}

export function factSourceLabel(fact: FactSourceLike): string {
  return fact.source_type
    .split("_")
    .filter(Boolean)
    .map((part, index) => (index === 0 ? part.charAt(0).toUpperCase() + part.slice(1) : part))
    .join(" ");
}

export function factSourceDetail(fact: FactSourceLike): string | null {
  const ref = fact.source_ref?.trim();
  return ref ? ref : null;
}

export function factSourceSummary(fact: FactSourceLike): string {
  const detail = factSourceDetail(fact);
  return detail ? `${factSourceLabel(fact)} · ${detail}` : factSourceLabel(fact);
}
