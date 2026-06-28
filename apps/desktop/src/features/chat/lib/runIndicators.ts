import type { UiMessage } from "@/stores/types";

type IndicatorMessage = Pick<UiMessage, "role" | "isMeta">;

export function awaitingFirstRunOutput(
  running: boolean,
  messages: IndicatorMessage[],
): boolean {
  if (!running) return false;

  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message.role === "assistant") return false;
    if (message.role === "user") return !message.isMeta;
  }

  return false;
}
