import { Plus } from "lucide-react";
import { type MCPServer } from "../../../api";
import { settingsErrorMessage } from "../../../lib/settingsLoadState";
import { SettingsConnectionHint, SettingsInlineError } from "../SettingsNotice";
import { ICON } from "../../../lib/icons";
import { SectionHeader } from "../../SectionHeader";
import { Empty } from "./atoms";
import { ServerRow } from "./ServerRow";

export function ServerList({
  servers,
  loadError,
  onAdd,
  onEdit,
  onChanged,
}: {
  servers: MCPServer[] | null;
  loadError: string | null;
  onAdd: () => void;
  onEdit: (name: string) => void;
  onChanged: () => Promise<void>;
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
              <button
                type="button"
                onClick={onAdd}
                className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-md bg-ink text-on-ink text-sm font-medium tracking-[-0.005em] hover:opacity-90 transition-opacity"
              >
                <Plus size={ICON.XS} strokeWidth={2.2} /> Add server
              </button>
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
