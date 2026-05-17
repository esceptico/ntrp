import { Suspense, lazy, useEffect, useState } from "react";
import { MotionConfig, motion } from "motion/react";
import { MOTION, EASE_EMPHASIZED } from "../lib/motion";
import { Sidebar } from "./Sidebar";
import { Chat } from "./Chat";
import { CommandPalette } from "./commandPalette/CommandPalette";
import { MarkdownViewer } from "./MarkdownViewer";
import { ApprovalReviewModal } from "./ApprovalReviewModal";
import { SidebarResizeHandle } from "./SidebarResizeHandle";
import { AgentRightSidebar } from "./AgentRightSidebar";
import { ErrorBoundary } from "./ErrorBoundary";

// The five "open from chrome" modals only mount when the user actually
// opens them. Lazy boundaries here keep ~300 KB of MCP/Providers/Memory/
// Automations code out of the initial bundle. Suspense fallback is null
// — modals are conditional anyway, no spinner needed for the brief
// chunk-fetch in an Electron renderer.
const SettingsModal = lazy(() =>
  import("./SettingsModal").then((m) => ({ default: m.SettingsModal })),
);
const AutomationsModal = lazy(() =>
  import("./AutomationsModal").then((m) => ({ default: m.AutomationsModal })),
);
const ArchiveModal = lazy(() =>
  import("./ArchiveModal").then((m) => ({ default: m.ArchiveModal })),
);
const MemoryModal = lazy(() =>
  import("./MemoryModal").then((m) => ({ default: m.MemoryModal })),
);
const ToolViewer = lazy(() =>
  import("./ToolViewer").then((m) => ({ default: m.ToolViewer })),
);
import { useStore } from "../store";
import { useEvents } from "../hooks/useEvents";
import { useActiveRuns } from "../hooks/useActiveRuns";
import { useAutomationEvents } from "../hooks/useAutomationEvents";
import { useThemeEffect } from "../lib/theme";
import { bootstrap, createSession, sendMessage } from "../actions";

function useHash(): string {
  const [hash, setHash] = useState(() => window.location.hash);
  useEffect(() => {
    const handler = () => setHash(window.location.hash);
    window.addEventListener("hashchange", handler);
    return () => window.removeEventListener("hashchange", handler);
  }, []);
  return hash;
}

export function App() {
  const hash = useHash();
  const currentSessionId = useStore((s) => s.currentSessionId);
  const sidebarHidden = useStore((s) => s.prefs.sidebarHidden);
  const sidebarWidth = useStore((s) => s.prefs.sidebarWidth);
  const toggleSidebar = useStore((s) => s.toggleSidebar);
  const openSettings = useStore((s) => s.openSettings);

  // Publish the sidebar width as a CSS var so the chat shell's
  // `left-[var(--sidebar-width,272px)]` can stay flush with the
  // sidebar's right edge as it resizes (without React having to
  // re-render Chat on every drag tick).
  useEffect(() => {
    document.documentElement.style.setProperty("--sidebar-width", `${sidebarWidth}px`);
  }, [sidebarWidth]);

  useThemeEffect();

  useEffect(() => {
    if (hash === "#trace-demo") return;
    void bootstrap();
  }, [hash]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && !e.altKey) {
        const k = e.key.toLowerCase();
        if (k === "b" && !e.shiftKey) {
          e.preventDefault();
          toggleSidebar();
          return;
        }
        if (k === "n" && !e.shiftKey) {
          e.preventDefault();
          void createSession();
          return;
        }
        if (e.key === ",") {
          e.preventDefault();
          openSettings();
          return;
        }
        return;
      }

      // Type-anywhere → focus composer. Apple Mail pattern: if the user
      // starts typing a printable character with nothing input-like
      // focused, jump focus into the composer and seed it with that
      // character so the keystroke isn't lost.
      if (e.altKey || e.metaKey || e.ctrlKey) return;
      if (e.key.length !== 1) return;
      const target = document.activeElement as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      ) {
        return;
      }
      const composer = document.getElementById("message-input") as HTMLTextAreaElement | null;
      if (!composer) return;
      e.preventDefault();
      const state = useStore.getState();
      state.setDraft(state.draft + e.key);
      composer.focus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggleSidebar, openSettings]);

  useEvents(hash === "#trace-demo" ? null : currentSessionId);
  useActiveRuns();
  useAutomationEvents();

  // Receive messages submitted from the quick-capture floating window.
  // The Electron main process forwards each one via `quick:message`;
  // we spin up a new session and immediately send the text. The user's
  // first interaction with the main window is the streaming response.
  useEffect(() => {
    const unsubscribe = window.ntrpDesktop?.quickCapture?.onMessage?.(async (message) => {
      try {
        await createSession();
        await sendMessage(message);
      } catch {
        /* surfaced via the store's error toast */
      }
    });
    return unsubscribe;
  }, []);

  // Push the user's chosen global shortcut to the main process every
  // time it changes. Main registers a default chord at startup but
  // doesn't know which key the user picked until the renderer pushes
  // it — prefs live in localStorage which the main process can't read.
  const quickCaptureShortcut = useStore((s) => s.prefs.quickCaptureShortcut);
  useEffect(() => {
    void window.ntrpDesktop?.quickCapture?.setShortcut?.(quickCaptureShortcut);
  }, [quickCaptureShortcut]);

  return (
    /* `reducedMotion="user"` makes every motion component honor the OS
       prefers-reduced-motion setting without per-call plumbing. The CSS
       @media (prefers-reduced-motion) block neutralizes CSS keyframes;
       this covers the JS-driven side (motion.div springs, layout anims,
       AnimatePresence). */
    <MotionConfig reducedMotion="user">
      <motion.div
        className="glass-surface glass-frosted glass-radius-md absolute top-2 left-2 bottom-2 z-30 w-[calc(var(--sidebar-width,272px)-16px)] rounded-xl overflow-hidden"
        initial={false}
        animate={{ x: sidebarHidden ? -sidebarWidth : 0 }}
        transition={{ duration: MOTION.route, ease: EASE_EMPHASIZED }}
      >
        <Sidebar />
        <SidebarResizeHandle />
      </motion.div>
      <ErrorBoundary>
        <Chat />
      </ErrorBoundary>
      <AgentRightSidebar />
      <ErrorBoundary>
        <Suspense fallback={null}>
          <SettingsModal />
          <AutomationsModal />
          <ArchiveModal />
          <MemoryModal />
          <ToolViewer />
        </Suspense>
      </ErrorBoundary>
      <CommandPalette />
      <MarkdownViewer />
      <ApprovalReviewModal />
    </MotionConfig>
  );
}
