export type FactSourceRefParts =
  | {
      kind: "chat_segment";
      session_id: string;
      message_start: number;
      message_end: number;
    }
  | {
      kind: string;
      [key: string]: unknown;
    };

export interface FactSourceLike {
  source_type: string;
  source_ref: string | null;
  source_ref_parts?: FactSourceRefParts | null;
}

export function factSourceLabel(fact: FactSourceLike): string {
  return fact.source_type
    .split("_")
    .filter(Boolean)
    .map((part, index) => (index === 0 ? part.charAt(0).toUpperCase() + part.slice(1) : part))
    .join(" ");
}

export function factSourceDetail(fact: FactSourceLike): string | null {
  if (fact.source_ref_parts?.kind === "chat_segment") {
    return `${fact.source_ref_parts.session_id} · messages ${fact.source_ref_parts.message_start}-${fact.source_ref_parts.message_end}`;
  }
  const ref = fact.source_ref?.trim();
  return ref ? ref : null;
}

export function factSourceSummary(fact: FactSourceLike): string {
  const detail = factSourceDetail(fact);
  return detail ? `${factSourceLabel(fact)} · ${detail}` : factSourceLabel(fact);
}
