import { Bot, Radio } from "lucide-react";
import { ICON } from "@/lib/icons";
import { BlurSwap } from "@/components/ui/BlurSwap";
import { StatusDot } from "@/features/background-agents/components/AgentRightSidebar";

type SessionIconState = "streaming" | "unread" | "channel" | "agent" | "idle";

/** Leading state glyph on each session row. Only rendered for
 *  states with something to indicate — streaming (animated dots in
 *  accent) and unread done (solid dot in accent-strong). Idle rows
 *  render an empty span that preserves the grid column width so the
 *  text alignment stays consistent across all rows. State changes
 *  crossfade through BlurSwap — the streaming→unread swap fires the
 *  moment a run completes, right when the user is watching the row. */
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
  const state: SessionIconState = streaming
    ? "streaming"
    : unread
      ? "unread"
      : isChannel
        ? "channel"
        : isAgent
          ? "agent"
          : "idle";

  return (
    <BlurSwap swapKey={state} blur={2}>
      {state === "streaming" ? (
        <span className="grid place-items-center w-4 h-4" aria-label="Running">
          <StatusDot status="running" pulse />
        </span>
      ) : state === "unread" ? (
        <span className="grid place-items-center w-4 h-4" aria-label="Unread">
          <span className="block w-[5px] h-[5px] rounded-full bg-accent-strong" />
        </span>
      ) : state === "channel" ? (
        <span
          className="grid place-items-center w-4 h-4 text-faint"
          aria-label="Channel"
          title="Channel — an automation posts its activity here; you can chat in it too"
        >
          <Radio size={ICON.SM} strokeWidth={2} />
        </span>
      ) : state === "agent" ? (
        <span
          className="grid place-items-center w-4 h-4 text-faint"
          aria-label="Agent"
          title="Agent session"
        >
          <Bot size={ICON.SM} strokeWidth={2} />
        </span>
      ) : (
        <span className="block w-4 h-4" aria-hidden />
      )}
    </BlurSwap>
  );
}
