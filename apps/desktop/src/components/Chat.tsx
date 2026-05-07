import clsx from "clsx";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useStore } from "../store";
import { Messages } from "./Messages";
import { Composer } from "./Composer";

function SidebarToggle() {
  const sidebarCollapsed = useStore((s) => s.prefs.sidebarCollapsed);
  const toggleSidebar = useStore((s) => s.toggleSidebar);
  const Icon = sidebarCollapsed ? PanelLeftOpen : PanelLeftClose;
  return (
    <button
      type="button"
      onClick={toggleSidebar}
      title={sidebarCollapsed ? "Expand sidebar (⌘B)" : "Collapse sidebar (⌘B)"}
      aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
      className="sidebar-toggle grid place-items-center w-[26px] h-[26px] rounded-md text-muted hover:bg-surface-soft hover:text-ink transition-colors"
    >
      <Icon size={14} strokeWidth={1.7} />
    </button>
  );
}

function ChatHeader() {
  const sessionId = useStore((s) => s.currentSessionId);
  const sessions = useStore((s) => s.sessions);
  const sidebarCollapsed = useStore((s) => s.prefs.sidebarCollapsed);
  const session = sessions.find((s) => s.session_id === sessionId);

  const title = session?.name || (sessionId ? "untitled" : "no session");
  const meta = sessionId ? sessionId.slice(0, 8) : "—";

  return (
    <div
      className={clsx(
        "chat-header flex items-center gap-3 h-[52px] pr-[18px]",
        sidebarCollapsed ? "pl-[88px]" : "pl-[18px]",
      )}
      style={{ transition: "padding-left 320ms cubic-bezier(0.32, 0.72, 0, 1)" }}
    >
      <SidebarToggle />
      <div className="flex-1 min-w-0 flex items-baseline gap-2.5">
        <h1 className="m-0 min-w-0 text-[14px] font-semibold tracking-[-0.01em] text-ink truncate">
          {title}
        </h1>
        <span className="shrink-0 text-[11.5px] text-faint font-mono tracking-[-0.01em]">
          {meta}
        </span>
      </div>
    </div>
  );
}

export function Chat() {
  const sidebarCollapsed = useStore((s) => s.prefs.sidebarCollapsed);
  const sessionId = useStore((s) => s.currentSessionId);
  return (
    <main
      data-sidebar-collapsed={sidebarCollapsed ? "true" : "false"}
      className="chat-shell grid grid-rows-[auto_minmax(0,1fr)_auto] bg-bg-main rounded-tl-xl overflow-hidden"
    >
      <ChatHeader />
      <Messages key={sessionId ?? "none"} />
      <Composer />
    </main>
  );
}
