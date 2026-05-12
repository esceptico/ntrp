import { useEffect, useState } from "react";
import { MotionConfig, motion } from "motion/react";
import { MOTION, EASE_EMPHASIZED } from "../lib/motion";
import { Sidebar } from "./Sidebar";
import { Chat } from "./Chat";
import { SettingsModal } from "./SettingsModal";
import { AutomationsModal } from "./AutomationsModal";
import { ArchiveModal } from "./ArchiveModal";
import { MemoryModal } from "./MemoryModal";
import { CommandPalette } from "./CommandPalette";
import { MarkdownViewer } from "./MarkdownViewer";
import { ToolViewer } from "./ToolViewer";
import { ApprovalReviewModal } from "./ApprovalReviewModal";
import { SidebarResizeHandle } from "./SidebarResizeHandle";
import { Demo as TraceDemo } from "./trace/Demo";
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
  // `left-[var(--sidebar-width,244px)]` can stay flush with the
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

  if (hash === "#trace-demo") {
    return <TraceDemo />;
  }

  return (
    /* `reducedMotion="user"` makes every motion component honor the OS
       prefers-reduced-motion setting without per-call plumbing. The CSS
       @media (prefers-reduced-motion) block neutralizes CSS keyframes;
       this covers the JS-driven side (motion.div springs, layout anims,
       AnimatePresence). */
    <MotionConfig reducedMotion="user">
      <motion.div
        className="absolute top-2 left-2 bottom-2 z-30 w-[calc(var(--sidebar-width,244px)-16px)] bg-bg-main border border-line rounded-xl shadow-sm overflow-hidden will-change-transform"
        initial={false}
        animate={{ x: sidebarHidden ? -sidebarWidth : 0 }}
        transition={{ duration: MOTION.route, ease: EASE_EMPHASIZED }}
      >
        <Sidebar />
        <SidebarResizeHandle />
      </motion.div>
      <Chat />
      <SettingsModal />
      <AutomationsModal />
      <ArchiveModal />
      <MemoryModal />
      <CommandPalette />
      <MarkdownViewer />
      <ToolViewer />
      <ApprovalReviewModal />
    </MotionConfig>
  );
}
