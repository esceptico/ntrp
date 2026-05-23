import { useState } from "react";
import { ArrowLeft, Trash2 } from "lucide-react";
import { useStore } from "../../../store";
import {
  type MCPServer,
  type MCPServerConfigPayload,
  type MCPTransport,
  addMCPServerApi,
  removeMCPServerApi,
  updateMCPServerApi,
} from "../../../api";
import { useMountedRef, useMutationState } from "../../../lib/hooks";
import { SettingsInlineError } from "../SettingsNotice";
import { ICON } from "../../../lib/icons";
import { GlassToggle } from "../../GlassToggle";
import { LabeledField } from "../Field";
import { type KeyVal } from "./editors";
import { buildMCPServerPayload, type MCPAuthMode } from "./payload";
import { HttpFields, StdioFields } from "./transportFields";
import { ToolsSection } from "./ToolsSection";

export function ServerForm({
  mode,
  server,
  onClose,
  onSaved,
  onRemoved,
}: {
  mode: "add" | "edit";
  server?: MCPServer;
  onClose: () => void;
  onSaved: () => Promise<void>;
  onRemoved?: () => Promise<void>;
}) {
  const config = useStore((s) => s.config);
  const mounted = useMountedRef();
  const { busy, error, run } = useMutationState(mounted);

  const initialTransport: MCPTransport =
    server?.transport === "http" || server?.transport === "stdio" ? server.transport : "http";

  const [name, setName] = useState(server?.name ?? "");
  const [transport, setTransport] = useState<MCPTransport>(initialTransport);

  // stdio fields
  const [command, setCommand] = useState(server?.command ?? "");
  const [argsList, setArgsList] = useState<string[]>(server?.args ?? [""]);
  const [envEntries, setEnvEntries] = useState<KeyVal[]>([{ key: "", value: "" }]);

  // http fields
  const [url, setUrl] = useState(server?.url ?? "");
  const [headerEntries, setHeaderEntries] = useState<KeyVal[]>([{ key: "", value: "" }]);
  const [auth, setAuth] = useState<MCPAuthMode>(server?.has_headers ? "headers" : "auto");

  function buildPayload(): MCPServerConfigPayload {
    return buildMCPServerPayload({
      transport,
      command,
      argsList,
      envEntries,
      url,
      headerEntries,
      auth,
    });
  }

  const valid =
    name.trim().length > 0 &&
    (transport === "stdio" ? command.trim().length > 0 : url.trim().length > 0);

  async function save() {
    if (!valid) return;
    const payload = buildPayload();
    await run(async () => {
      if (mode === "add") {
        await addMCPServerApi(config, name.trim(), payload);
      } else if (server) {
        await updateMCPServerApi(config, server.name, payload);
      }
      await onSaved();
    });
  }

  async function remove() {
    if (!server) return;
    if (!confirm(`Uninstall MCP server "${server.name}"? This cannot be undone.`)) return;
    await run(async () => {
      await removeMCPServerApi(config, server.name);
      if (onRemoved) await onRemoved();
    });
  }

  const transportLocked = mode === "edit";

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={onClose}
          className="inline-flex items-center gap-1.5 h-7 px-1.5 rounded-md text-sm text-muted hover:text-ink transition-colors"
        >
          <ArrowLeft size={ICON.SM} strokeWidth={2} /> Back
        </button>
        {mode === "edit" && server && (
          <button
            type="button"
            onClick={() => void remove()}
            disabled={busy}
            className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-md text-sm font-medium text-bad bg-bad-soft hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            <Trash2 size={ICON.SM} strokeWidth={2} /> Uninstall
          </button>
        )}
      </div>

      <h3 className="m-0 text-lg font-semibold tracking-[-0.012em] text-ink">
        {mode === "add" ? "Connect to a custom MCP" : `Update ${server?.name} MCP`}
      </h3>

      <div className="grid gap-3">
        <LabeledField label="Name">
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={mode === "edit"}
            placeholder="MCP server name"
            spellCheck={false}
            className="w-full h-8 px-2.5 rounded-md border border-line-soft bg-surface text-base text-ink outline-none focus:border-line transition-colors disabled:bg-surface-soft disabled:text-muted"
          />
        </LabeledField>

        {transportLocked ? (
          <div className="inline-flex items-center h-8 px-3 rounded-md bg-surface-soft border border-line-soft text-sm font-medium text-ink-soft self-start">
            {transport === "stdio" ? "STDIO" : "Streamable HTTP"}
          </div>
        ) : (
          <GlassToggle
            size="sm"
            value={transport}
            onChange={(v) => setTransport(v as MCPTransport)}
            options={[
              { value: "stdio", label: "STDIO" },
              { value: "http", label: "Streamable HTTP" },
            ]}
          />
        )}

        {transportLocked && (
          <p className="m-0 text-xs text-faint">
            To switch transport type, uninstall first.
          </p>
        )}

        {transport === "stdio" ? (
          <StdioFields
            command={command}
            onCommand={setCommand}
            argsList={argsList}
            onArgs={setArgsList}
            envEntries={envEntries}
            onEnv={setEnvEntries}
          />
        ) : (
          <HttpFields
            url={url}
            onUrl={setUrl}
            headerEntries={headerEntries}
            onHeaders={setHeaderEntries}
            auth={auth}
            onAuth={setAuth}
          />
        )}
      </div>

      {mode === "edit" && server && server.tools.length > 0 && (
        <ToolsSection server={server} onChanged={onSaved} />
      )}

      {error && <SettingsInlineError title="Couldn't save MCP server" message={error} />}

      <div className="flex justify-end pt-1">
        <button
          type="button"
          onClick={() => void save()}
          disabled={!valid || busy}
          className="inline-flex items-center h-8 px-3.5 rounded-[9px] bg-ink text-on-ink text-sm font-medium tracking-[-0.005em] hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {busy ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}
