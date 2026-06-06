import { Bot, Radio } from "lucide-react";
import { ICON } from "../../lib/icons";
import { StatusDot } from "../AgentRightSidebar";

/** Leading state glyph on each session row. Only rendered for
 *  states with something to indicate — streaming (animated dots in
 *  accent) and unread done (solid dot in accent-strong). Idle rows
 *  return an empty span that preserves the grid column width so the
 *  text alignment stays consistent across all rows. */
export function SessionStateIcon({
  streaming,
  unread,
  isChannel,
  isAgent,
}: {
  streaming: boolean;
  unread: boolean;
  isChannel: boolean;
  isAgent: boolean;
}) {
  if (streaming) {
    return (
      <span className="grid place-items-center w-4 h-4" aria-label="Running">
        <StatusDot status="running" pulse />
      </span>
    );
  }
  if (unread) {
    return (
      <span className="grid place-items-center w-4 h-4" aria-label="Unread">
        <span className="block w-[5px] h-[5px] rounded-full bg-accent-strong" />
      </span>
    );
  }
  if (isChannel) {
    return (
      <span
        className="grid place-items-center w-4 h-4 text-faint"
        aria-label="Channel"
        title="Channel — an automation posts its activity here; you can chat in it too"
      >
        <Radio size={ICON.SM} strokeWidth={2} />
      </span>
    );
  }
  if (isAgent) {
    return (
      <span
        className="grid place-items-center w-4 h-4 text-faint"
        aria-label="Agent"
        title="Agent session"
      >
        <Bot size={ICON.SM} strokeWidth={2} />
      </span>
    );
  }
  return <span aria-hidden />;
}
