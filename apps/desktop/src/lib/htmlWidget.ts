import type { ActivityItem } from "../store";

export interface HtmlWidgetResolution {
  action: "accept" | "decline" | "cancel";
  values: Record<string, unknown>;
}

/** Parse render_html tool-call args ({"html","title","mode"}). History
 *  rebuild path — result `data` is not persisted to the transcript. */
export function htmlWidgetFromArgs(args: string | undefined): ActivityItem["htmlWidget"] | undefined {
  if (!args) return undefined;
  try {
    const parsed = JSON.parse(args);
    if (typeof parsed?.html !== "string" || typeof parsed?.title !== "string") return undefined;
    if (parsed.mode !== "display" && parsed.mode !== "input") return undefined;
    return { html: parsed.html, title: parsed.title, mode: parsed.mode };
  } catch {
    return undefined;
  }
}

/** History-rebuild lift. Input-mode calls whose persisted result is not an
 *  action envelope (fail-fast "no interactive client" error, run stopped
 *  mid-input) stay plain rows — matching the live stream, which never sets
 *  htmlWidget for them. A still-pending input re-lifts via the replayed
 *  input_needed event. */
export function htmlWidgetFromHistory(
  args: string | undefined,
  resultContent: string | undefined,
): ActivityItem["htmlWidget"] | undefined {
  const widget = htmlWidgetFromArgs(args);
  if (widget?.mode === "input" && resolutionFromResult(resultContent) === null) return undefined;
  return widget;
}

/** The frozen-state badge source: input-mode result content IS the envelope. */
export function resolutionFromResult(result: string | undefined): HtmlWidgetResolution | null {
  if (!result) return null;
  try {
    const parsed = JSON.parse(result);
    if (parsed?.action === "accept" || parsed?.action === "decline" || parsed?.action === "cancel") {
      return { action: parsed.action, values: parsed.values ?? {} };
    }
  } catch {
    // error result, not an envelope
  }
  return null;
}
