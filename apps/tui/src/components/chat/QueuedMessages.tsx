import type { QueuedMessage } from "../../stores/streamingStore.js";
import { colors } from "../ui/colors.js";
import { truncateText } from "../../lib/utils.js";

interface QueuedMessagesProps {
  items: QueuedMessage[];
  onCancel: (clientId: string) => void;
}

export function QueuedMessages({ items, onCancel }: QueuedMessagesProps) {
  if (items.length === 0) return null;

  return (
    <box flexShrink={0} flexDirection="column" marginBottom={1}>
      {items.map((q) => {
        const isCancelling = q.status === "cancelling";
        const isFailed = q.status === "failed";
        return (
          <box key={q.clientId} flexDirection="row" paddingLeft={2} paddingRight={2}>
            <box flexGrow={1} overflow="hidden">
              <text>
                <span fg={colors.text.disabled}>queued · </span>
                <span fg={isFailed ? colors.status.error : colors.text.muted}>
                  {truncateText(q.text, 80)}
                </span>
                {isFailed ? <span fg={colors.status.error}> · failed</span> : null}
              </text>
            </box>
            <box marginLeft={1} onMouseDown={() => !isCancelling && onCancel(q.clientId)}>
              <text>
                <span fg={isCancelling ? colors.text.disabled : colors.status.warning}>
                  {isCancelling ? "…" : "✕"}
                </span>
              </text>
            </box>
          </box>
        );
      })}
    </box>
  );
}
