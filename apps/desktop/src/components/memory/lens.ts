import type {
  MemoryFeedback,
  MemoryItem,
  MemoryKind,
  MemoryProvenance,
} from "../../api/memoryItems";
import type { BadgeTone } from "../Badge";

// ── Kind palette ──────────────────────────────────────────────────────────
// The single color ramp shared by rail glyphs, claim subject badges, and the
// provenance graph nodes — one claim, three faces, one color. Flexoki
// mid-tones that read on warm-light + dark.
export const KIND_COLOR: Record<MemoryKind, string> = {
  claim: "#da702c", // flexoki orange
  lens: "#8b7ec8", // flexoki violet
};

// An entity lens (lens_exclusive) gets its own gold so the rail reads the
// difference between a topic view and a named subject.
export const ENTITY_COLOR = "#d0a215"; // flexoki yellow
export const USER_COLOR = "#3aa99f"; // flexoki cyan — user-authored

/** The dot color for a lens row / node, accounting for entity + user lenses. */
export function lensColor(item: MemoryItem): string {
  if (item.lens_exclusive) return ENTITY_COLOR;
  if (item.provenance === "user_authored") return USER_COLOR;
  return KIND_COLOR.lens;
}

export function nodeColor(item: MemoryItem): string {
  return item.kind === "lens" ? lensColor(item) : KIND_COLOR.claim;
}

// ── Provenance / feedback tone mapping ──────────────────────────────────────
const PROVENANCE_TONE: Record<MemoryProvenance, BadgeTone> = {
  user_authored: "accent",
  recorded: "neutral",
  inferred: "neutral",
  external: "neutral",
  induced: "warn",
};

export function provenanceTone(p: MemoryProvenance): BadgeTone {
  return PROVENANCE_TONE[p];
}

const PROVENANCE_LABEL: Record<MemoryProvenance, string> = {
  user_authored: "you wrote",
  recorded: "recorded",
  inferred: "inferred",
  external: "external",
  induced: "induced",
};

export function provenanceLabel(p: MemoryProvenance): string {
  return PROVENANCE_LABEL[p];
}

export function feedbackTone(f: MemoryFeedback): BadgeTone {
  if (f === "confirmed") return "ok";
  if (f === "corrected") return "warn";
  return "neutral";
}

// ── Display helpers ─────────────────────────────────────────────────────────
export function lensTitle(item: MemoryItem): string {
  return item.lens_name ?? item.content ?? "Untitled lens";
}

export function scopeLabel(scope: { kind: string; key: string | null }): string {
  return scope.key ? `${scope.kind}:${scope.key}` : scope.kind;
}

export function truncate(text: string, max: number): string {
  const t = text.replace(/\s+/g, " ").trim();
  return t.length > max ? `${t.slice(0, max)}…` : t;
}

/** Relative-time string for a freshness / recency stamp. Null-safe. */
export function relativeTime(iso: string | null): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const diff = Date.now() - then;
  const m = Math.round(diff / 60_000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  if (d < 30) return `${d}d ago`;
  const mo = Math.round(d / 30);
  if (mo < 12) return `${mo}mo ago`;
  return `${Math.round(mo / 12)}y ago`;
}
