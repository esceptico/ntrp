import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { Sidebar } from "./Sidebar";
import { Chat } from "./Chat";
import { SettingsModal } from "./SettingsModal";
import { AutomationsModal } from "./AutomationsModal";
import { ArchiveModal } from "./ArchiveModal";
import { MemoryModal } from "./MemoryModal";
import { CommandPalette } from "./CommandPalette";
import { MarkdownViewer } from "./MarkdownViewer";
import { ToolViewer } from "./ToolViewer";
import { Demo as TraceDemo } from "./trace/Demo";
import { useStore } from "../store";
import { useEvents } from "../hooks/useEvents";
import { useThemeEffect } from "../lib/theme";
import { bootstrap, createSession } from "../actions";

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
  const toggleSidebar = useStore((s) => s.toggleSidebar);
  const openSettings = useStore((s) => s.openSettings);

  useThemeEffect();

  useEffect(() => {
    if (hash === "#trace-demo") return;
    void bootstrap();
  }, [hash]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (!mod || e.altKey) return;
      const k = e.key.toLowerCase();
      if (k === "b" && !e.shiftKey) {
        e.preventDefault();
        toggleSidebar();
      } else if (k === "n" && !e.shiftKey) {
        e.preventDefault();
        void createSession();
      } else if (e.key === ",") {
        e.preventDefault();
        openSettings();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggleSidebar, openSettings]);

  useEvents(hash === "#trace-demo" ? null : currentSessionId);

  if (hash === "#trace-demo") {
    return <TraceDemo />;
  }

  return (
    <>
      <motion.div
        className="sidebar-wrap"
        initial={false}
        animate={{ x: sidebarHidden ? -244 : 0 }}
        transition={{ duration: 0.32, ease: [0.32, 0.72, 0, 1] }}
      >
        <Sidebar />
      </motion.div>
      <Chat />
      <SettingsModal />
      <AutomationsModal />
      <ArchiveModal />
      <MemoryModal />
      <CommandPalette />
      <MarkdownViewer />
      <ToolViewer />
    </>
  );
}
