import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { useStore } from "@/stores";
import { type MCPServer, listMCPServersApi } from "@/api/settings";
import { RISE_IN, RISE_SETTLED, DISSOLVE_OUT, MOTION, EASE_EMPHASIZED } from "@/lib/tokens/motion";
import { TabPanels } from "@/components/ui/TabPanels";
import { ServerForm } from "@/features/settings/components/mcp/ServerForm";
import { ServerList } from "@/features/settings/components/mcp/ServerList";
import { SetupAssistant } from "@/features/settings/components/setup/SetupAssistant";

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
      <AnimatePresence>
        {assistantOpen && (
          <motion.div
            initial={RISE_IN}
            animate={RISE_SETTLED}
            exit={DISSOLVE_OUT}
            transition={{ duration: MOTION.panel, ease: EASE_EMPHASIZED }}
          >
            <SetupAssistant
              kind="mcp"
              onClose={() => setAssistantOpen(false)}
              onDone={async () => {
                setAssistantOpen(false);
                await refresh();
              }}
            />
          </motion.div>
        )}
      </AnimatePresence>
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
