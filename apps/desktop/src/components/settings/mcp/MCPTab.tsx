import { useEffect, useState } from "react";
import { useStore } from "../../../store";
import { type MCPServer, listMCPServersApi } from "../../../api";
import { ServerForm } from "./ServerForm";
import { ServerList } from "./ServerList";

type View = { kind: "list" } | { kind: "add" } | { kind: "edit"; name: string };

export function MCPTab() {
  const config = useStore((s) => s.config);
  const [servers, setServers] = useState<MCPServer[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [view, setView] = useState<View>({ kind: "list" });

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

  if (view.kind === "add") {
    return (
      <ServerForm
        mode="add"
        onClose={() => setView({ kind: "list" })}
        onSaved={async () => {
          await refresh();
          setView({ kind: "list" });
        }}
      />
    );
  }
  if (view.kind === "edit") {
    const server = servers?.find((s) => s.name === view.name);
    if (!server) {
      setView({ kind: "list" });
      return null;
    }
    return (
      <ServerForm
        mode="edit"
        server={server}
        onClose={() => setView({ kind: "list" })}
        onSaved={async () => {
          await refresh();
        }}
        onRemoved={async () => {
          await refresh();
          setView({ kind: "list" });
        }}
      />
    );
  }

  return (
    <ServerList
      servers={servers}
      loadError={loadError}
      onAdd={() => setView({ kind: "add" })}
      onEdit={(name) => setView({ kind: "edit", name })}
      onChanged={refresh}
    />
  );
}
