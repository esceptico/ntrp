import { useEffect } from "react";
import { Sidebar } from "./Sidebar";
import { Chat } from "./Chat";
import { SettingsModal } from "./SettingsModal";
import { useStore } from "../store";
import { useEvents } from "../hooks/useEvents";
import { bootstrap } from "../actions";

export function App() {
  const currentSessionId = useStore((s) => s.currentSessionId);
  const settingsOpen = useStore((s) => s.settingsOpen);

  useEffect(() => {
    void bootstrap();
  }, []);

  useEvents(currentSessionId);

  return (
    <>
      <Sidebar />
      <Chat />
      {settingsOpen && <SettingsModal />}
    </>
  );
}
