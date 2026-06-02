import type {
  Lens,
  LensProvenance,
  MemoryFeedback,
  MemoryItem,
  MemoryProvenance,
} from "../../api/memoryItems";
import type { BadgeTone } from "../Badge";

// ── Claim color ramp ────────────────────────────────────────────────────────
// The graph has no lens nodes — every node is a claim. Differentiate claims by
// provenance (never by shape). Flexoki mid-tones that read on warm-light + dark.
const PROVENANCE_COLOR: Record<MemoryProvenance, string> = {
  user_authored: "#3aa99f", // flexoki cyan — you wrote it
  recorded: "#da702c", // flexoki orange — captured
  inferred: "#8b7ec8", // flexoki violet — inferred
  external: "#879a39", // flexoki green — external
};

/** Node color for a claim, keyed on provenance (not kind — there are no kinds). */
export function nodeColor(item: MemoryItem): string {
  return PROVENANCE_COLOR[item.provenance] ?? PROVENANCE_COLOR.recorded;
}

// A lens rail dot color, keyed on the view's provenance (user-authored vs induced).
const LENS_COLOR: Record<LensProvenance, string> = {
  user_authored: "#3aa99f", // flexoki cyan
  induced: "#8b7ec8", // flexoki violet
};

export function lensColor(lens: Lens): string {
  return LENS_COLOR[lens.provenance] ?? LENS_COLOR.user_authored;
}

export function lensProvenanceTone(p: LensProvenance): BadgeTone {
  return p === "induced" ? "warn" : "accent";
}

export function lensProvenanceLabel(p: LensProvenance): string {
  return p === "induced" ? "induced" : "you wrote";
}

// ── Provenance / feedback tone mapping ──────────────────────────────────────
const PROVENANCE_TONE: Record<MemoryProvenance, BadgeTone> = {
  user_authored: "accent",
  recorded: "neutral",
  inferred: "neutral",
  external: "neutral",
};

export function provenanceTone(p: MemoryProvenance): BadgeTone {
  return PROVENANCE_TONE[p];
}

const PROVENANCE_LABEL: Record<MemoryProvenance, string> = {
  user_authored: "you wrote",
  recorded: "recorded",
  inferred: "inferred",
  external: "external",
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
export function lensTitle(lens: Lens): string {
  return lens.name || "Untitled lens";
}

/** Clean one-line preview of a lens criterion for list subtitles. The criterion is
 *  structured markdown (`## Belongs\n<sentence>\n## Profile shape\n- …`); show the
 *  Belongs sentence, never the raw `## Belongs` heading/bullets. */
export function criterionPreview(criterion: string): string {
  if (!criterion) return "";
  const lines = criterion.split("\n");
  const belongsIdx = lines.findIndex((l) => /^#{1,6}\s*belongs\b/i.test(l.trim()));
  if (belongsIdx !== -1) {
    const body: string[] = [];
    for (let i = belongsIdx + 1; i < lines.length; i++) {
      if (/^#{1,6}\s/.test(lines[i].trim())) break; // next section
      body.push(lines[i]);
    }
    const sentence = body.join(" ").trim();
    if (sentence) return sentence;
  }
  // No Belongs section — strip any markdown heading/bullet markers and flatten.
  return criterion
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/^[-*]\s+/gm, "")
    .replace(/\s+/g, " ")
    .trim();
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
