import type { MessageSourceFocus } from "./messageSourceFocus";

export type FactSourceRefParts =
  | {
      kind: "chat_segment";
      session_id: string;
      message_start: number;
      message_end: number;
    }
  | {
      kind: "chat_message_range";
      session_id: string;
      message_start_id: string;
      message_end_id: string;
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

export type FactChatSourceFocus = Omit<MessageSourceFocus, "nonce">;
export type FactSourceStatusTone = "neutral" | "ok" | "warn";

export interface FactSourceStatus {
  label: string;
  tone: FactSourceStatusTone;
}

function chatSegmentParts(parts: FactSourceRefParts | null | undefined): Extract<FactSourceRefParts, { kind: "chat_segment" }> | null {
  if (parts?.kind !== "chat_segment") return null;
  if (typeof parts.session_id !== "string") return null;
  if (typeof parts.message_start !== "number") return null;
  if (typeof parts.message_end !== "number") return null;
  return parts as Extract<FactSourceRefParts, { kind: "chat_segment" }>;
}

function chatMessageRangeParts(parts: FactSourceRefParts | null | undefined): Extract<FactSourceRefParts, { kind: "chat_message_range" }> | null {
  if (parts?.kind !== "chat_message_range") return null;
  if (typeof parts.session_id !== "string") return null;
  if (typeof parts.message_start_id !== "string") return null;
  if (typeof parts.message_end_id !== "string") return null;
  return parts as Extract<FactSourceRefParts, { kind: "chat_message_range" }>;
}

export function factSourceLabel(fact: FactSourceLike): string {
  return fact.source_type
    .split("_")
    .filter(Boolean)
    .map((part, index) => (index === 0 ? part.charAt(0).toUpperCase() + part.slice(1) : part))
    .join(" ");
}

export function factSourceDetail(fact: FactSourceLike): string | null {
  const chatRange = chatMessageRangeParts(fact.source_ref_parts);
  if (chatRange) {
    if (chatRange.message_start_id === chatRange.message_end_id) {
      return `${chatRange.session_id} · message ${chatRange.message_start_id}`;
    }
    return `${chatRange.session_id} · messages ${chatRange.message_start_id}-${chatRange.message_end_id}`;
  }
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

export function factSourceStatus(fact: FactSourceLike): FactSourceStatus {
  if (fact.source_type === "chat") {
    return factChatSourceFocus(fact)
      ? { label: "Openable source", tone: "ok" }
      : { label: "Source link unavailable", tone: "warn" };
  }
  if (fact.source_type === "explicit" && !fact.source_ref?.trim()) {
    return { label: "Manual entry", tone: "neutral" };
  }
  if (fact.source_ref?.trim()) {
    return { label: "Source reference", tone: "neutral" };
  }
  return { label: "No source reference", tone: "warn" };
}

export function factChatSourceSessionId(fact: FactSourceLike): string | null {
  return factChatSourceFocus(fact)?.sessionId ?? null;
}

export function factChatSourceFocus(fact: FactSourceLike): FactChatSourceFocus | null {
  if (fact.source_type !== "chat") return null;
  const chatRange = chatMessageRangeParts(fact.source_ref_parts);
  if (chatRange) {
    return {
      sessionId: chatRange.session_id,
      messageStartId: chatRange.message_start_id,
      messageEndId: chatRange.message_end_id,
    };
  }
  const chatSegment = chatSegmentParts(fact.source_ref_parts);
  if (!chatSegment) return null;
  return {
    sessionId: chatSegment.session_id,
    messageStart: chatSegment.message_start,
    messageEnd: chatSegment.message_end,
  };
}
