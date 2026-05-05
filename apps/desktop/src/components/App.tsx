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
import { bootstrap } from "../actions";

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

  useThemeEffect();

  useEffect(() => {
    if (hash === "#trace-demo") return;
    void bootstrap();
  }, [hash]);

  // Cmd/Ctrl+B toggles the sidebar — matches Cursor / VSCode.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "b" && !e.shiftKey && !e.altKey) {
        e.preventDefault();
        toggleSidebar();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggleSidebar]);

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
