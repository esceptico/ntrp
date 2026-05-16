import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Plus, Settings as SettingsIcon, Trash2 } from "lucide-react";
import clsx from "clsx";
import { useStore } from "../../store";
import {
  type MCPServer,
  type MCPServerConfigPayload,
  type ToolOverrideDecision,
  type MCPTransport,
  addMCPServerApi,
  listMCPServersApi,
  removeMCPServerApi,
  startMCPOAuthApi,
  toggleMCPServerApi,
  updateMCPServerApi,
  updateMCPToolsApi,
} from "../../api";
import { fetchServerConfig, updateServerConfig } from "../../actions";
import { useMountedRef, useMutationState } from "../../lib/hooks";
import { settingsErrorMessage } from "../../lib/settingsLoadState";
import { SettingsConnectionHint, SettingsInlineError } from "./SettingsNotice";
import { ICON } from "../../lib/icons";
import { GlassToggle } from "../GlassToggle";

type View = { kind: "list" } | { kind: "add" } | { kind: "edit"; name: string };

const TOOL_DECISIONS: Array<{ value: ToolOverrideDecision; label: string }> = [
  { value: "approve", label: "Approve" },
  { value: "ask", label: "Ask" },
  { value: "deny", label: "Deny" },
];

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

// ─── List view ────────────────────────────────────────────────────────

function ServerList({
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
        <div className="flex items-center justify-between gap-3">
          <h3 className="m-0 text-sm font-medium uppercase tracking-[0.06em] text-faint">
            Servers
          </h3>
          {!loadError && (
            <button
              type="button"
              onClick={onAdd}
              className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-md bg-ink text-on-ink text-sm font-medium tracking-[-0.005em] hover:opacity-90 transition-opacity"
            >
              <Plus size={ICON.XS} strokeWidth={2.2} /> Add server
            </button>
          )}
        </div>

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
          <ul className="rounded-[10px] border border-line-soft bg-bg-main/30 divide-y divide-line-soft m-0 p-0 list-none">
            {servers.map((s) => (
              <ServerRow key={s.name} server={s} onEdit={() => onEdit(s.name)} onChanged={onChanged} />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function ServerRow({
  server,
  onEdit,
  onChanged,
}: {
  server: MCPServer;
  onEdit: () => void;
  onChanged: () => Promise<void>;
}) {
  const config = useStore((s) => s.config);
  const mounted = useMountedRef();
  const { busy, error, run } = useMutationState(mounted);

  const onToggle = () =>
    void run(async () => {
      await toggleMCPServerApi(config, server.name, !server.enabled);
      await onChanged();
    });

  const onAuthenticate = () =>
    void run(async () => {
      await startMCPOAuthApi(config, server.name);
      await onChanged();
    });

  const needsAuth = server.auth === "oauth" && !server.connected;
  const subtitleParts: string[] = [];
  subtitleParts.push(server.transport.toUpperCase());
  if (server.connected) subtitleParts.push(`${server.tool_count} tools`);
  else if (server.error) subtitleParts.push("error");
  else if (!server.enabled) subtitleParts.push("disabled");
  else subtitleParts.push("disconnected");

  return (
    <li className="flex items-center gap-3 px-3.5 py-2.5">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span
            aria-hidden
            className={clsx(
              "w-1.5 h-1.5 rounded-full shrink-0",
              server.connected ? "bg-ok" : server.error ? "bg-bad" : "bg-line",
            )}
          />
          <span className="text-base font-medium text-ink tracking-[-0.005em] truncate">
            {server.name}
          </span>
        </div>
        <div className="mt-0.5 ml-3.5 text-xs text-faint tabular-nums">
          {subtitleParts.join(" · ")}
        </div>
        {(error || server.error) && (
          <div
            className="mt-1 ml-3.5 text-xs text-bad truncate"
            title={error ?? server.error ?? ""}
          >
            {error ?? server.error}
          </div>
        )}
      </div>
      <div className="flex items-center gap-1 shrink-0">
        {needsAuth && (
          <button
            type="button"
            onClick={onAuthenticate}
            disabled={busy}
            className="h-7 px-2.5 rounded-md text-xs font-medium tracking-[-0.005em] text-ink-soft border border-line-soft hover:bg-surface-soft hover:text-ink transition-colors disabled:opacity-50"
          >
            {busy ? "…" : "Authenticate"}
          </button>
        )}
        <button
          type="button"
          onClick={onEdit}
          aria-label="Configure"
          className="grid place-items-center w-7 h-7 rounded-md text-muted hover:bg-surface-soft hover:text-ink transition-colors"
        >
          <SettingsIcon size={ICON.MD} strokeWidth={2} />
        </button>
        <Toggle checked={server.enabled} onChange={onToggle} disabled={busy} />
      </div>
    </li>
  );
}

// ─── Add / edit form ──────────────────────────────────────────────────

function ServerForm({
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

  function buildPayload(): MCPServerConfigPayload {
    if (transport === "stdio") {
      const env = kvToRecord(envEntries);
      return {
        transport: "stdio",
        command: command.trim(),
        args: argsList.map((a) => a.trim()).filter(Boolean),
        ...(env ? { env } : {}),
      };
    }
    const headers = kvToRecord(headerEntries);
    return {
      transport: "http",
      url: url.trim(),
      ...(headers ? { headers } : {}),
    };
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
        <Field label="Name">
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={mode === "edit"}
            placeholder="MCP server name"
            spellCheck={false}
            className="w-full h-8 px-2.5 rounded-md border border-line-soft bg-surface text-base text-ink outline-none focus:border-line transition-colors disabled:bg-surface-soft disabled:text-muted"
          />
        </Field>

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

// ─── Tools whitelist ──────────────────────────────────────────────────

function ToolsSection({
  server,
  onChanged,
}: {
  server: MCPServer;
  onChanged: () => Promise<void>;
}) {
  const config = useStore((s) => s.config);
  const serverConfig = useStore((s) => s.serverConfig);
  const mounted = useMountedRef();
  const { busy, error, run } = useMutationState(mounted);
  const overrides = serverConfig?.tool_overrides ?? {};

  const enabledNames = useMemo(
    () => new Set(server.tools.filter((t) => t.enabled).map((t) => t.name)),
    [server.tools],
  );

  function commit(next: Set<string>) {
    // null means "all tools enabled" (no whitelist).
    const allEnabled = next.size === server.tools.length;
    const tools = allEnabled ? null : Array.from(next);
    void run(async () => {
      await updateMCPToolsApi(config, server.name, tools);
      await onChanged();
    });
  }

  function baseDecision(tool: MCPServer["tools"][number]): ToolOverrideDecision {
    return tool.policy.requires_approval ? "ask" : "approve";
  }

  function setToolDecision(tool: MCPServer["tools"][number], decision: ToolOverrideDecision) {
    const next = { ...overrides };
    if (decision === baseDecision(tool)) delete next[tool.full_name];
    else next[tool.full_name] = decision;
    void run(async () => {
      await updateServerConfig({ tool_overrides: next });
      await fetchServerConfig();
      await onChanged();
    });
  }

  return (
    <div className="grid gap-2">
      <h4 className="m-0 text-xs font-medium uppercase tracking-[0.06em] text-faint">
        Tools ({server.tools.length})
      </h4>
      <ul className="rounded-md border border-line-soft bg-bg-main/30 divide-y divide-line-soft m-0 p-0 list-none">
        {server.tools.map((t) => {
          const checked = enabledNames.has(t.name);
          return (
            <li key={t.name} className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-start gap-3 px-3 py-2">
              <input
                type="checkbox"
                checked={checked}
                disabled={busy}
                onChange={() => {
                  const next = new Set(enabledNames);
                  if (checked) next.delete(t.name);
                  else next.add(t.name);
                  commit(next);
                }}
                className="mt-[3px] shrink-0 cursor-pointer"
              />
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-ink tracking-[-0.005em] truncate">
                  {t.name}
                </div>
                {t.description && (
                  <div className="text-xs text-faint leading-snug line-clamp-2">
                    {t.description}
                  </div>
                )}
              </div>
              <GlassToggle
                size="sm"
                value={overrides[t.full_name] ?? baseDecision(t)}
                onChange={(v) => setToolDecision(t, v as ToolOverrideDecision)}
                options={TOOL_DECISIONS.map((d) => ({ value: d.value, label: d.label }))}
              />
            </li>
          );
        })}
      </ul>
      {error && <SettingsInlineError title="Couldn't update tools" message={error} />}
    </div>
  );
}

// ─── Field helpers ────────────────────────────────────────────────────

interface KeyVal {
  key: string;
  value: string;
}

function kvToRecord(entries: KeyVal[]): Record<string, string> | null {
  const out: Record<string, string> = {};
  for (const e of entries) {
    const k = e.key.trim();
    if (!k) continue;
    out[k] = e.value;
  }
  return Object.keys(out).length === 0 ? null : out;
}

function StdioFields({
  command,
  onCommand,
  argsList,
  onArgs,
  envEntries,
  onEnv,
}: {
  command: string;
  onCommand: (v: string) => void;
  argsList: string[];
  onArgs: (v: string[]) => void;
  envEntries: KeyVal[];
  onEnv: (v: KeyVal[]) => void;
}) {
  return (
    <>
      <Field label="Command to launch">
        <input
          type="text"
          value={command}
          onChange={(e) => onCommand(e.target.value)}
          placeholder="openai-dev-mcp serve-sqlite"
          spellCheck={false}
          className="w-full h-8 px-2.5 rounded-md border border-line-soft bg-surface text-base text-ink outline-none focus:border-line transition-colors font-mono"
        />
      </Field>

      <Field label="Arguments">
        <ListEditor
          values={argsList}
          onChange={onArgs}
          placeholder=""
          addLabel="Add argument"
          mono
        />
      </Field>

      <Field label="Environment variables">
        <KeyValueEditor entries={envEntries} onChange={onEnv} addLabel="Add environment variable" />
      </Field>
    </>
  );
}

function HttpFields({
  url,
  onUrl,
  headerEntries,
  onHeaders,
}: {
  url: string;
  onUrl: (v: string) => void;
  headerEntries: KeyVal[];
  onHeaders: (v: KeyVal[]) => void;
}) {
  return (
    <>
      <Field label="URL">
        <input
          type="text"
          value={url}
          onChange={(e) => onUrl(e.target.value)}
          placeholder="https://mcp.example.com/mcp"
          spellCheck={false}
          className="w-full h-8 px-2.5 rounded-md border border-line-soft bg-surface text-base text-ink outline-none focus:border-line transition-colors font-mono"
        />
      </Field>

      <Field label="Headers">
        <KeyValueEditor entries={headerEntries} onChange={onHeaders} addLabel="Add header" />
      </Field>
    </>
  );
}

function ListEditor({
  values,
  onChange,
  placeholder,
  addLabel,
  mono,
}: {
  values: string[];
  onChange: (v: string[]) => void;
  placeholder: string;
  addLabel: string;
  mono?: boolean;
}) {
  const update = (i: number, v: string) => {
    const next = values.slice();
    next[i] = v;
    onChange(next);
  };
  const remove = (i: number) => {
    const next = values.filter((_, idx) => idx !== i);
    onChange(next.length === 0 ? [""] : next);
  };
  return (
    <div className="grid gap-1.5">
      {values.map((v, i) => (
        <div key={i} className="flex items-center gap-1.5">
          <input
            type="text"
            value={v}
            onChange={(e) => update(i, e.target.value)}
            placeholder={placeholder}
            spellCheck={false}
            className={clsx(
              "flex-1 h-8 px-2.5 rounded-md border border-line-soft bg-surface text-base text-ink outline-none focus:border-line transition-colors",
              mono && "font-mono",
            )}
          />
          <RemoveBtn onClick={() => remove(i)} />
        </div>
      ))}
      <AddBtn label={addLabel} onClick={() => onChange([...values, ""])} />
    </div>
  );
}

function KeyValueEditor({
  entries,
  onChange,
  addLabel,
}: {
  entries: KeyVal[];
  onChange: (v: KeyVal[]) => void;
  addLabel: string;
}) {
  const update = (i: number, patch: Partial<KeyVal>) => {
    const next = entries.slice();
    next[i] = { ...next[i], ...patch };
    onChange(next);
  };
  const remove = (i: number) => {
    const next = entries.filter((_, idx) => idx !== i);
    onChange(next.length === 0 ? [{ key: "", value: "" }] : next);
  };
  return (
    <div className="grid gap-1.5">
      {entries.map((e, i) => (
        <div key={i} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] gap-1.5">
          <input
            type="text"
            value={e.key}
            onChange={(ev) => update(i, { key: ev.target.value })}
            placeholder="Key"
            spellCheck={false}
            className="h-8 px-2.5 rounded-md border border-line-soft bg-surface text-base text-ink outline-none focus:border-line transition-colors font-mono"
          />
          <input
            type="text"
            value={e.value}
            onChange={(ev) => update(i, { value: ev.target.value })}
            placeholder="Value"
            spellCheck={false}
            className="h-8 px-2.5 rounded-md border border-line-soft bg-surface text-base text-ink outline-none focus:border-line transition-colors font-mono"
          />
          <RemoveBtn onClick={() => remove(i)} />
        </div>
      ))}
      <AddBtn label={addLabel} onClick={() => onChange([...entries, { key: "", value: "" }])} />
    </div>
  );
}

function AddBtn({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center justify-center gap-1.5 h-8 rounded-md bg-surface-soft hover:bg-surface-soft/80 text-sm text-muted hover:text-ink transition-colors"
    >
      <Plus size={ICON.XS} strokeWidth={2} /> {label}
    </button>
  );
}

function RemoveBtn({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="Remove"
      className="grid place-items-center w-8 h-8 rounded-md text-faint hover:text-ink hover:bg-surface-soft transition-colors"
    >
      <Trash2 size={ICON.SM} strokeWidth={2} />
    </button>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="grid gap-1.5">
      <span className="text-sm font-medium tracking-[-0.005em] text-ink-soft">{label}</span>
      {children}
    </label>
  );
}

function Toggle({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean;
  onChange: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={onChange}
      className={clsx(
        "relative inline-flex items-center h-[18px] w-[30px] rounded-full transition-colors shrink-0",
        checked ? "bg-accent-strong" : "bg-line",
        disabled && "opacity-50 cursor-not-allowed",
      )}
    >
      <span
        aria-hidden
        className={clsx(
          "absolute top-[2px] w-[14px] h-[14px] rounded-full bg-white transition-transform",
          checked ? "translate-x-[14px]" : "translate-x-[2px]",
        )}
      />
    </button>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-3 py-6 rounded-[10px] bg-bg-main/40 text-sm text-faint italic text-center">
      {children}
    </div>
  );
}
