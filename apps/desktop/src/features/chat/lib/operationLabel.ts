import type { ActivityItem } from "@/stores";

/** Semantic icon key for a step — mapped to a lucide glyph in the trace row.
 *  `null` falls back to a plain timeline dot (unknown tools). */
export type StepIconKey =
  | "search"
  | "globe"
  | "folder"
  | "file"
  | "edit"
  | "file-plus"
  | "terminal"
  | "brain"
  | "list"
  | null;

export interface OperationLabel {
  /** Natural-language operation, e.g. "Read", "Searched the web". */
  verb: string;
  /** The object of the operation (a path / query / command), or null. */
  detail: string | null;
  /** Semantic icon for the step. */
  iconKey: StepIconKey;
}

// ponytail: heuristic kind→(verb, icon) map. The real "operation header" (a
// per-step natural-language label + icon) belongs to the server, which would
// supersede this. Until then this turns the raw tool name into a readable
// operation label and falls back to the tool's own displayName/kind + a plain
// dot when the kind isn't known. Order matters: more specific first.
//
// Matched against a separator-normalized kind ("read_file" → "read file") so
// `\b` guards behave for both snake_case and short ambiguous tokens — without
// the normalize, `\bread\b` would miss "read_file" (`_` is a word char) and a
// bare `read`/`cat`/`view` would wrongly claim "preview"/"category".
const RULES: ReadonlyArray<readonly [RegExp, string, StepIconKey]> = [
  [/\bweb ?search\b|\bsearch ?web\b|\b(exa|ddg|google|brave|tavily)\b/, "Searched the web", "search"],
  [/\bweb ?fetch\b|\bfetch\b|\bcurl\b|\bhttp\b|\bbrowse\b|\bscrape\b|\bopen ?url\b|\burl\b/, "Fetched", "globe"],
  [/\bgrep\b|\bripgrep\b|\brg\b|\bsearch ?(code|files?|repo|symbols?)\b/, "Searched code", "search"],
  [/\bglob\b|\bfind\b|\blist ?(dir|files?)\b|\bls\b/, "Listed files", "folder"],
  [/\bread\b|\bcat\b|\bview\b|\bopen ?file\b|\bget ?file\b/, "Read", "file"],
  [/\bstr ?replace\b|\bapply ?patch\b|\bpatch\b|\bedit\b|\bupdate ?file\b|\bmodify\b/, "Edited", "edit"],
  [/\bwrite\b|\bcreate ?file\b|\bsave ?file\b/, "Wrote", "file-plus"],
  [/\bbash\b|\bshell\b|\bexec\b|\brun ?(command|shell)\b|\bterminal\b|\bcmd\b/, "Ran", "terminal"],
  [/\bmemory\b|\brecall\b|\bremember\b|\bfact\b|observ/, "Memory", "brain"],
  [/\bsearch\b/, "Searched", "search"],
  [/\btodo\b|\bplan\b/, "Updated plan", "list"],
  [/\bthink\b|\breason\b/, "Thought", "brain"],
];

// Args keys that name the object of the call, in priority order.
const DETAIL_KEYS = [
  "path", "file_path", "filename", "file", "query", "q", "command", "cmd",
  "url", "pattern", "name", "prompt", "task", "title",
] as const;

const MAX_DETAIL = 64;

function titleCase(s: string): string {
  const cleaned = s.replace(/[_-]+/g, " ").trim();
  if (!cleaned) return s;
  return cleaned[0].toUpperCase() + cleaned.slice(1);
}

function truncate(s: string): string {
  const t = s.trim().replace(/\s+/g, " ");
  return t.length > MAX_DETAIL ? `${t.slice(0, MAX_DETAIL - 1)}…` : t;
}

function parseArgs(args: string | undefined): Record<string, unknown> | null {
  if (!args) return null;
  try {
    const parsed = JSON.parse(args);
    return parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : null;
  } catch {
    return null; // partial JSON mid-stream; detail/sources fill in once it lands.
  }
}

function detailFromArgs(obj: Record<string, unknown> | null): string | null {
  if (!obj) return null;
  for (const key of DETAIL_KEYS) {
    const v = obj[key];
    if (typeof v === "string" && v.trim()) return truncate(v);
  }
  return null;
}

/** Map a tool activity item to a natural-language operation label + icon.
 *  Agents carry their own friendly name and task, so they keep their bespoke
 *  row and never reach this. */
export function operationLabel(item: ActivityItem): OperationLabel {
  // Normalize separators to spaces so `\b` word-boundaries match cleanly.
  const kind = (item.kind ?? "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  const matched = RULES.find(([re]) => re.test(kind));
  const verb = matched ? matched[1] : titleCase(item.displayName || item.kind || "Tool");
  const iconKey = matched ? matched[2] : null;
  return { verb, detail: detailFromArgs(parseArgs(item.args)), iconKey };
}

function hostname(raw: string): string | null {
  const s = raw.trim();
  if (!s) return null;
  try {
    return new URL(s).hostname.replace(/^www\./, "");
  } catch {
    // Bare "github.com/x" or "example.com" — take the leading authority.
    const m = s.match(/^(?:https?:\/\/)?([a-z0-9.-]+\.[a-z]{2,})(?:[/:?#]|$)/i);
    return m ? m[1].replace(/^www\./, "") : null;
  }
}

/** Source chips for a step — domains the call touched. Honest: only what we
 *  can read from args (a `url`/`urls`). Result-derived sources need the server
 *  to surface them. Empty for most tools. */
export function stepSources(item: ActivityItem): string[] {
  const obj = parseArgs(item.args);
  if (!obj) return [];
  const raw: string[] = [];
  if (typeof obj.url === "string") raw.push(obj.url);
  if (Array.isArray(obj.urls)) raw.push(...obj.urls.filter((u): u is string => typeof u === "string"));
  const seen = new Set<string>();
  for (const u of raw) {
    const h = hostname(u);
    if (h) seen.add(h);
  }
  return [...seen].slice(0, 3);
}
