import { useLayoutEffect, useRef } from "react";
import clsx from "clsx";
import { PanelLeftClose, PanelLeftOpen, Radio } from "lucide-react";
import { useStore } from "../store";
import { Messages } from "./Messages";
import { Composer } from "./Composer";
import { ApprovalBanner } from "./ApprovalBanner";
import { ProgressiveBlurOverlay } from "./ScrollBlur";
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
      <Icon size={ICON.MD} strokeWidth={2} />
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
      </div>
    </div>
  );
}

export function Chat() {
  const sidebarHidden = useStore((s) => s.prefs.sidebarHidden);
  const sessionId = useStore((s) => s.currentSessionId);
  const hasApproval = useStore((s) => s.pendingApprovals.length > 0);

  // Composer overlays the bottom of the message scroll area so messages
  // pass behind its glass via backdrop-filter (Rauno's Depth essay:
  // "Shoot through a surface"). The scroll area needs padding-bottom
  // equal to the bottom stack's actual height so the last message
  // clears the composer when scrolled to the end. Height is dynamic
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
        <ProgressiveBlurOverlay
          edge="top"
          className="absolute left-0 right-0 top-0 z-[5]"
          style={{ height: "52px" }}
        />
        <div className="absolute top-0 left-0 right-0 z-10">
          <ChatHeader />
        </div>
        {/* SidebarToggle lives outside the glassy header — backdrop-filter
            creates a containing block for `position: fixed` descendants,
            which would tether the toggle to the header instead of the
            viewport. Keeping it at the main level preserves its fixed-
            to-viewport anchor near the macOS traffic lights. */}
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
