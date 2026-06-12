import { submitToolResult } from "../api";
import { getState } from "../store";
import type { HtmlWidgetResolution } from "../lib/htmlWidget";

/** Resolve a blocked render_html input call. Returns false when the POST
 *  failed (card should unfreeze). */
export async function respondToHtmlInput(
  toolId: string,
  action: HtmlWidgetResolution["action"],
  values: Record<string, unknown>,
): Promise<boolean> {
  const s = getState();
  if (!s.currentRunId) return false;
  try {
    await submitToolResult(s.config, {
      run_id: s.currentRunId,
      tool_id: toolId,
      result: JSON.stringify({ action, values }),
      approved: true,
    });
    return true;
  } catch (error) {
    s.appendMessage({
      id: crypto.randomUUID(),
      role: "error",
      content: error instanceof Error ? error.message : "Failed to submit widget input",
    });
    return false;
  }
}
