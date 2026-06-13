import { useEffect, useState } from "react";
import { useStore } from "../../../store";
import { type MCPServer, listMCPServersApi } from "../../../api";
import { TabPanels } from "../../ui/TabPanels";
import { ServerForm } from "./ServerForm";
import { ServerList } from "./ServerList";
import { SetupAssistant } from "../setup/SetupAssistant";

type View = { kind: "list" } | { kind: "add" } | { kind: "edit"; name: string };

export function MCPTab() {
  const config = useStore((s) => s.config);
  const [servers, setServers] = useState<MCPServer[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [view, setView] = useState<View>({ kind: "list" });
  const [assistantOpen, setAssistantOpen] = useState(false);

  async function refresh() {
    setLoadError(null);
    try {
      const r = await listMCPServersApi(config);
      setServers(r.servers);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : String(err));
      setServers([]);
    }
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const editing = view.kind === "edit" ? servers?.find((s) => s.name === view.name) : undefined;
  if (view.kind === "edit" && !editing) {
    setView({ kind: "list" });
    return null;
  }

  return (
    <TabPanels
      value={view.kind === "edit" ? `edit:${view.name}` : view.kind}
      direction={view.kind === "list" ? -1 : 1}
    >
      {assistantOpen && (
        <SetupAssistant
          kind="mcp"
          onClose={() => setAssistantOpen(false)}
          onDone={async () => {
            setAssistantOpen(false);
            await refresh();
          }}
        />
      )}
      {view.kind === "add" ? (
        <ServerForm
          mode="add"
          onClose={() => setView({ kind: "list" })}
          onSaved={async () => {
            await refresh();
            setView({ kind: "list" });
          }}
        />
      ) : view.kind === "edit" && editing ? (
        <ServerForm
          mode="edit"
          server={editing}
          onClose={() => setView({ kind: "list" })}
          onSaved={async () => {
            await refresh();
          }}
          onRemoved={async () => {
            await refresh();
            setView({ kind: "list" });
          }}
        />
      ) : (
        <ServerList
          servers={servers}
          loadError={loadError}
          onAdd={() => setView({ kind: "add" })}
          onEdit={(name) => setView({ kind: "edit", name })}
          onChanged={refresh}
          onAssistant={() => setAssistantOpen(true)}
        />
      )}
    </TabPanels>
  );
}
