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

function chatSegmentParts(parts: FactSourceRefParts | null | undefined): Extract<FactSourceRefParts, { kind: "chat_segment" }> | null {
  if (parts?.kind !== "chat_segment") return null;
  if (typeof parts.session_id !== "string") return null;
  if (typeof parts.message_start !== "number") return null;
  if (typeof parts.message_end !== "number") return null;
  return parts as Extract<FactSourceRefParts, { kind: "chat_segment" }>;
}

export function factSourceLabel(fact: FactSourceLike): string {
  return fact.source_type
    .split("_")
    .filter(Boolean)
    .map((part, index) => (index === 0 ? part.charAt(0).toUpperCase() + part.slice(1) : part))
    .join(" ");
}

export function factSourceDetail(fact: FactSourceLike): string | null {
  const chatSegment = chatSegmentParts(fact.source_ref_parts);
  if (chatSegment) {
    return `${chatSegment.session_id} · messages ${chatSegment.message_start}-${chatSegment.message_end}`;
  }
  const ref = fact.source_ref?.trim();
  return ref ? ref : null;
}

export function factSourceSummary(fact: FactSourceLike): string {
  const detail = factSourceDetail(fact);
  return detail ? `${factSourceLabel(fact)} · ${detail}` : factSourceLabel(fact);
}

export function factChatSourceSessionId(fact: FactSourceLike): string | null {
  if (fact.source_type !== "chat") return null;
  return chatSegmentParts(fact.source_ref_parts)?.session_id ?? null;
}
