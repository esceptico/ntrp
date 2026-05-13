import clsx from "clsx";
import { PanelLeftClose, PanelLeftOpen, Radio } from "lucide-react";
import { useStore } from "../store";
import { Messages } from "./Messages";
import { Composer } from "./Composer";
import { ApprovalBanner } from "./ApprovalBanner";
import { ICON } from "../lib/icons";

function SidebarToggle() {
  const sidebarHidden = useStore((s) => s.prefs.sidebarHidden);
  const toggleSidebar = useStore((s) => s.toggleSidebar);
  const Icon = sidebarHidden ? PanelLeftOpen : PanelLeftClose;
  return (
    <button
      type="button"
      onClick={toggleSidebar}
      title={sidebarHidden ? "Show sidebar (⌘B)" : "Hide sidebar (⌘B)"}
      aria-label={sidebarHidden ? "Show sidebar" : "Hide sidebar"}
      className="sidebar-toggle grid place-items-center w-[22px] h-[22px] rounded-md text-muted hover:bg-surface-soft hover:text-ink transition-colors"
    >
      <Icon size={ICON.MD} strokeWidth={1.5} />
    </button>
  );
}

function ChatHeader() {
  const sessionId = useStore((s) => s.currentSessionId);
  const sessions = useStore((s) => s.sessions);
  const automations = useStore((s) => s.automations);
  const sidebarHidden = useStore((s) => s.prefs.sidebarHidden);
  const session = sessions.find((s) => s.session_id === sessionId);

  const title = session?.name || (sessionId ? "untitled" : "no session");
  const meta = sessionId ? sessionId.slice(0, 8) : "—";
  const isChannel = session?.session_type === "channel";
  const originId = session?.origin_automation_id ?? null;
  const originAutomation = originId
    ? (automations ?? []).find((a) => a.task_id === originId)
    : null;
  // Fall back to a shortened ID when the parent automation isn't in the
  // current automations list (e.g. it was deleted, or the cache hasn't
  // loaded yet). The user still sees something concrete to point at.
  const originLabel = originAutomation?.name || (originId ? originId.slice(0, 8) : null);

  return (
    <div
      className={clsx(
        "chat-header flex items-center gap-3 h-[52px] pr-[18px] transition-[padding-left] duration-route ease-emphasized",
        sidebarHidden ? "pl-[128px]" : "pl-[18px]",
      )}
    >
      <SidebarToggle />
      <div className="flex-1 min-w-0 flex items-baseline gap-2.5">
        <h1 className="m-0 min-w-0 text-md font-semibold tracking-[-0.01em] text-ink truncate">
          {title}
        </h1>
        {isChannel && (
          <span
            className="inline-flex items-center gap-1 shrink-0 px-1.5 h-[18px] rounded-full bg-surface-soft text-2xs font-medium uppercase tracking-[0.06em] text-muted self-center"
            title="Channel session — an agent-spawned feed"
          >
            <Radio size={ICON.XS} strokeWidth={2} />
            channel
          </span>
        )}
        {isChannel && originLabel && (
          <span className="shrink-0 text-xs text-faint truncate" title={originId ?? undefined}>
            from {originLabel}
          </span>
        )}
        <span className="shrink-0 text-xs text-faint font-mono tracking-[-0.01em]">
          {meta}
        </span>
      </div>
    </div>
  );
}

export function Chat() {
  const sidebarHidden = useStore((s) => s.prefs.sidebarHidden);
  const sessionId = useStore((s) => s.currentSessionId);
  return (
    <main
      data-sidebar-hidden={sidebarHidden ? "true" : "false"}
      className="absolute top-0 right-0 bottom-0 left-[var(--sidebar-width,244px)] data-[sidebar-hidden=true]:left-0 transition-[left] duration-route ease-emphasized grid grid-rows-[auto_minmax(0,1fr)_auto_auto] bg-bg overflow-hidden"
    >
      <ChatHeader />
      <Messages key={sessionId ?? "none"} />
      <ApprovalBanner />
      <Composer />
    </main>
  );
}
