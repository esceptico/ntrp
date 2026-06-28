import { Plus } from "lucide-react";
import type { MCPServer } from "@/api/settings";
import { settingsErrorMessage } from "@/features/settings/lib/settingsLoadState";
import { SettingsConnectionHint, SettingsInlineError } from "@/features/settings/components/SettingsNotice";
import { ICON } from "@/lib/icons";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { Button } from "@/components/ui/Button";
import { Empty } from "@/features/settings/components/mcp/atoms";
import { ServerRow } from "@/features/settings/components/mcp/ServerRow";

export function ServerList({
  servers,
  loadError,
  onAdd,
  onEdit,
  onChanged,
  onAssistant,
}: {
  servers: MCPServer[] | null;
  loadError: string | null;
  onAdd: () => void;
  onEdit: (name: string) => void;
  onChanged: () => Promise<void>;
  onAssistant: () => void;
}) {
  return (
    <div className="grid gap-4">
      <div>
        <p className="m-0 text-sm text-muted leading-[1.45] max-w-[460px]">
          Connect external tools and data sources via Model Context Protocol.
        </p>
      </div>

      <div className="grid gap-2">
        <SectionHeader
          label="Servers"
          action={
            !loadError && (
              <div className="flex flex-wrap gap-2">
                <Button variant="secondary" size="sm" onClick={onAssistant}>
                  Run setup assistant
                </Button>
                <Button size="sm" onClick={onAdd}>
                  <Plus size={ICON.XS} strokeWidth={2.2} /> Add server
                </Button>
              </div>
            )
          }
        />

        {servers === null ? (
          <Empty>Loading…</Empty>
        ) : loadError ? (
          <div className="grid gap-3">
            <SettingsInlineError
              title="Couldn't load MCP servers"
              message={settingsErrorMessage(loadError)}
            />
            <SettingsConnectionHint />
          </div>
        ) : servers.length === 0 ? (
          <Empty>No MCP servers yet.</Empty>
        ) : (
          <ul className="min-w-0 overflow-hidden rounded-[10px] border border-line-soft bg-bg-main/30 divide-y divide-line-soft m-0 p-0 list-none">
            {servers.map((s) => (
              <ServerRow key={s.name} server={s} onEdit={() => onEdit(s.name)} onChanged={onChanged} />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
