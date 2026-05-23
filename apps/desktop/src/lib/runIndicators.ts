import type { UiMessage } from "../store/types";

type IndicatorMessage = Pick<UiMessage, "role" | "isMeta">;

export function awaitingFirstRunOutput(
  running: boolean,
  lastMessage: IndicatorMessage | null | undefined,
): boolean {
  return Boolean(running && lastMessage?.role === "user" && !lastMessage.isMeta);
}
