import { useLayoutEffect, useRef } from "react";
import clsx from "clsx";
import { ArrowLeft, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useStore } from "../store";
import { switchSession } from "../actions";
import { Messages } from "./Messages";
import { Composer } from "./Composer";
import { ApprovalBanner } from "./ApprovalBanner";
import { IconButton } from "./IconButton";
import { ICON } from "../lib/icons";

function SidebarToggle() {
  const sidebarHidden = useStore((s) => s.prefs.sidebarHidden);
  const toggleSidebar = useStore((s) => s.toggleSidebar);
  const Icon = sidebarHidden ? PanelLeftOpen : PanelLeftClose;
  return (
    <IconButton
      size="xs"
      className="sidebar-toggle"
      onClick={toggleSidebar}
      title={sidebarHidden ? "Show sidebar (⌘B)" : "Hide sidebar (⌘B)"}
      aria-label={sidebarHidden ? "Show sidebar" : "Hide sidebar"}
    >
      <Icon size={ICON.MD} strokeWidth={2} />
    </IconButton>
  );
}

function ChatHeader() {
  const sessionId = useStore((s) => s.currentSessionId);
  const sessions = useStore((s) => s.sessions);
  const sidebarHidden = useStore((s) => s.prefs.sidebarHidden);
  const session = sessions.find((s) => s.session_id === sessionId);

  const title = session?.name || (sessionId ? "untitled" : "no session");

  // A child agent session gets a breadcrumb back to its parent in the header —
  // the discoverable spot, mirroring the hub's "← parent" chip.
  const parentId = session?.parent_session_id ?? null;
  const isAgent = session?.session_type === "agent" || !!parentId;
  const parentName =
    (parentId ? sessions.find((s) => s.session_id === parentId)?.name : null)?.trim() || "parent session";

  return (
    <div
      className={clsx(
        "chat-header flex items-center gap-2 h-[52px] pr-[18px] transition-[padding-left] duration-route ease-emphasized",
        sidebarHidden ? "pl-[128px]" : "pl-[18px]",
      )}
    >
      {isAgent && parentId && (
        <>
          <button
            type="button"
            onClick={() => void switchSession(parentId)}
            title={`Back to ${parentName}`}
            className="group/back shrink-0 inline-flex items-center gap-1 h-[26px] max-w-[180px] rounded-md px-1.5 -ml-0.5 text-sm text-muted hover:text-ink hover:bg-surface-soft transition-colors"
          >
            <ArrowLeft
              size={ICON.SM}
              strokeWidth={2}
              className="shrink-0 text-faint transition-colors group-hover/back:text-ink"
            />
            <span className="truncate">{parentName}</span>
          </button>
          <span className="shrink-0 text-faint select-none" aria-hidden>
            /
          </span>
        </>
      )}
      <h1 className="m-0 min-w-0 flex-1 text-md font-semibold tracking-[-0.01em] text-ink truncate">
        {title}
      </h1>
    </div>
  );
}

export function Chat() {
  const sidebarHidden = useStore((s) => s.prefs.sidebarHidden);
  const sessionId = useStore((s) => s.currentSessionId);
  const hasApproval = useStore((s) => s.pendingApprovals.length > 0);

  // Composer overlays the bottom of the message scroll area. The scroll
  // area needs padding-bottom equal to the bottom stack's actual height
  // so the last message clears the composer when scrolled to the end.
  // Height is dynamic
  // (textarea auto-resize, approval banner appears/disappears), so we
  // observe it and write to `--chat-bottom-h` consumed by
  // `.scroll-messages` padding-bottom + the jump-to-bottom pill offset.
  const bottomStackRef = useRef<HTMLDivElement>(null);
  // useLayoutEffect (not useEffect) so the measured height is written
  // BEFORE first paint — otherwise the scroll-padding briefly uses the
  // CSS fallback (96px) and the pill uses its inline fallback (96px),
  // causing a one-frame jump when the real composer is taller. Per
  // Codex review.
  useLayoutEffect(() => {
    const el = bottomStackRef.current;
    if (!el) return;
    const apply = (height: number) => {
      document.documentElement.style.setProperty("--chat-bottom-h", `${height}px`);
    };
    apply(el.getBoundingClientRect().height);
    const ro = new ResizeObserver((entries) => {
      const h = entries[0]?.contentRect.height ?? 0;
      apply(h);
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
      document.documentElement.style.removeProperty("--chat-bottom-h");
    };
  }, []);

  return (
    <main
      data-sidebar-hidden={sidebarHidden ? "true" : "false"}
      data-has-approval={hasApproval ? "true" : "false"}
      className="absolute top-0 right-0 bottom-0 left-[var(--sidebar-width,272px)] data-[sidebar-hidden=true]:left-0 transition-[left] duration-route ease-emphasized bg-bg overflow-hidden"
    >
      <div className="relative w-full h-full">
        <Messages key={sessionId ?? "none"} />
        <div
          aria-hidden
          className="chat-bottom-fade absolute left-0 right-0 bottom-0 pointer-events-none z-[5]"
          style={{ height: "calc(var(--chat-bottom-h, 96px) + 24px)" }}
        />
        <div className="absolute top-0 left-0 right-0 z-10">
          <ChatHeader />
        </div>
        {/* SidebarToggle lives outside the header so it keeps its fixed
            viewport anchor near the macOS traffic lights. */}
        <SidebarToggle />
        <div
          ref={bottomStackRef}
          className="absolute bottom-0 left-0 right-0 z-10"
        >
          <ApprovalBanner />
          <Composer />
        </div>
      </div>
    </main>
  );
}
