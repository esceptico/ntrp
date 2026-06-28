import type { ActivityItem } from "@/stores";

export interface OperationLabel {
  /** Natural-language operation, e.g. "Read", "Searched the web". */
  verb: string;
  /** The object of the operation (a path / query / command), or null. */
  detail: string | null;
}

// ponytail: heuristic kind→verb map. The real "operation header" (a per-step
// natural-language label) belongs to the server, which would supersede this.
// Until then this turns the raw tool name into a readable operation label and
// falls back to the tool's own displayName/kind when the kind isn't known.
// Order matters: more specific patterns first (file-search before web-search).
//
// Matched against a separator-normalized kind ("read_file" → "read file") so
// `\b` guards behave for both snake_case and short ambiguous tokens — without
// the normalize, `\bread\b` would miss "read_file" (`_` is a word char) and a
// bare `read`/`cat`/`view` would wrongly claim "preview"/"category".
const RULES: ReadonlyArray<readonly [RegExp, string]> = [
  [/\bweb ?search\b|\bsearch ?web\b|\b(exa|ddg|google|brave|tavily)\b/, "Searched the web"],
  [/\bweb ?fetch\b|\bfetch\b|\bcurl\b|\bhttp\b|\bbrowse\b|\bscrape\b|\bopen ?url\b|\burl\b/, "Fetched"],
  [/\bgrep\b|\bripgrep\b|\brg\b|\bsearch ?(code|files?|repo|symbols?)\b/, "Searched code"],
  [/\bglob\b|\bfind\b|\blist ?(dir|files?)\b|\bls\b/, "Listed files"],
  [/\bread\b|\bcat\b|\bview\b|\bopen ?file\b|\bget ?file\b/, "Read"],
  [/\bstr ?replace\b|\bapply ?patch\b|\bpatch\b|\bedit\b|\bupdate ?file\b|\bmodify\b/, "Edited"],
  [/\bwrite\b|\bcreate ?file\b|\bsave ?file\b/, "Wrote"],
  [/\bbash\b|\bshell\b|\bexec\b|\brun ?(command|shell)\b|\bterminal\b|\bcmd\b/, "Ran"],
  [/\bmemory\b|\brecall\b|\bremember\b|\bfact\b|observ/, "Memory"],
  [/\bsearch\b/, "Searched"],
  [/\btodo\b|\bplan\b/, "Updated plan"],
  [/\bthink\b|\breason\b/, "Thought"],
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

function detailFromArgs(args: string | undefined): string | null {
  if (!args) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(args);
  } catch {
    return null; // partial JSON mid-stream; the detail fills in once it lands.
  }
  if (!parsed || typeof parsed !== "object") return null;
  const obj = parsed as Record<string, unknown>;
  for (const key of DETAIL_KEYS) {
    const v = obj[key];
    if (typeof v === "string" && v.trim()) return truncate(v);
  }
  return null;
}

/** Map a tool activity item to a natural-language operation label. Agents
 *  carry their own friendly name and task, so they keep their bespoke row. */
export function operationLabel(item: ActivityItem): OperationLabel {
  // Normalize separators to spaces so `\b` word-boundaries match cleanly.
  const kind = (item.kind ?? "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  const matched = RULES.find(([re]) => re.test(kind));
  const verb = matched ? matched[1] : titleCase(item.displayName || item.kind || "Tool");
  return { verb, detail: detailFromArgs(item.args) };
}
