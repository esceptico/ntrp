import { useEffect, useState } from "react";
import { Sidebar } from "./Sidebar";
import { Chat } from "./Chat";
import { SettingsModal } from "./SettingsModal";
import { MarkdownViewer } from "./MarkdownViewer";
import { ToolViewer } from "./ToolViewer";
import { Demo as TraceDemo } from "./trace/Demo";
import { useStore } from "../store";
import { useEvents } from "../hooks/useEvents";
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

  useEffect(() => {
    if (hash === "#trace-demo") return;
    void bootstrap();
  }, [hash]);

  useEvents(hash === "#trace-demo" ? null : currentSessionId);

  if (hash === "#trace-demo") {
    return <TraceDemo />;
  }

  return (
    <>
      <Sidebar />
      <Chat />
      <SettingsModal />
      <MarkdownViewer />
      <ToolViewer />
    </>
  );
}
