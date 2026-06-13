import { useMemo, useState } from "react";
import type { MCPServerConfigPayload, MCPTransport, SetupStatus } from "../../../api";
import { addMCPServerApi, getSetupStatusApi, startMCPOAuthApi } from "../../../api";
import { useStore } from "../../../store";
import { parseKeyValueLines, parseMCPServerImport, splitLines } from "../../../lib/setupAssistant";
import { SettingsInlineError } from "../SettingsNotice";

export function MCPSetupAssistant({ onDone }: { onDone: () => Promise<void> | void }) {
  const config = useStore((s) => s.config);
  const [transport, setTransport] = useState<MCPTransport>("stdio");
  const [name, setName] = useState("");
  const [command, setCommand] = useState("");
  const [argsText, setArgsText] = useState("");
  const [envText, setEnvText] = useState("");
  const [url, setUrl] = useState("");
  const [headersText, setHeadersText] = useState("");
  const [jsonText, setJsonText] = useState("");
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [savedName, setSavedName] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const imported = useMemo(() => {
    if (!jsonText.trim()) return null;
    try {
      return parseMCPServerImport(jsonText);
    } catch {
      return null;
    }
  }, [jsonText]);

  async function run(label: string, fn: () => Promise<void>) {
    setBusy(label);
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  function buildGuidedPayload(): { name: string; payload: MCPServerConfigPayload } {
    const serverName = name.trim();
    if (!serverName) throw new Error("MCP server name is required.");
    if (transport === "stdio") {
      if (!command.trim()) throw new Error("STDIO command is required.");
      const env = parseKeyValueLines(envText);
      return { name: serverName, payload: { transport: "stdio", command: command.trim(), args: splitLines(argsText), ...(env ? { env } : {}) } };
    }
    if (!url.trim()) throw new Error("HTTP URL is required.");
    const headers = parseKeyValueLines(headersText);
    return { name: serverName, payload: { transport: "http", url: url.trim(), ...(headers ? { headers } : {}) } };
  }

  async function save() {
    await run("save", async () => {
      const parsed = jsonText.trim() ? parseMCPServerImport(jsonText) : null;
      const guided = parsed ? null : buildGuidedPayload();
      const serverName = parsed?.name ?? guided!.name;
      const payload = parsed?.config ?? guided!.payload;
      await addMCPServerApi(config, serverName, payload);
      setSavedName(serverName);
      setStatus(await getSetupStatusApi(config));
      setSaved(true);
    });
  }

  async function refresh() {
    await run("refresh", async () => {
      setStatus(await getSetupStatusApi(config));
    });
  }

  async function reauthenticate() {
    if (!savedName) return;
    await run("oauth", async () => {
      await startMCPOAuthApi(config, savedName);
      setStatus(await getSetupStatusApi(config));
    });
  }

  return (
    <div className="grid gap-4">
      {error && <SettingsInlineError title="MCP setup error" message={error} />}
      <section className="grid gap-2">
        <div className="text-sm font-medium text-ink">1. Choose transport</div>
        <div className="flex flex-wrap gap-2">
          {[
            ["stdio", "STDIO", "Run a local command and connect over stdin/stdout."],
            ["http", "HTTP", "Connect to a streamable HTTP MCP endpoint."],
          ].map(([id, label, detail]) => (
            <label key={id} className="rounded-md border border-line-soft bg-surface-soft/35 px-3 py-2 text-sm">
              <input type="radio" className="mr-2" checked={transport === id} onChange={() => setTransport(id as MCPTransport)} />
              <span className="font-medium text-ink-soft">{label}</span>
              <span className="block pl-5 text-xs text-muted">{detail}</span>
            </label>
          ))}
        </div>
      </section>

      <section className="grid gap-2">
        <div className="text-sm font-medium text-ink">2. Guided fields or JSON import</div>
        <p className="m-0 text-xs text-muted">Args, env, and headers accept one entry per line. Env/header lines use KEY=value.</p>
        <input className="input-field" value={name} onChange={(e) => setName(e.target.value)} placeholder="Server name" disabled={Boolean(jsonText.trim())} />
        {transport === "stdio" ? (
          <>
            <input className="input-field" value={command} onChange={(e) => setCommand(e.target.value)} placeholder="Command, e.g. npx" disabled={Boolean(jsonText.trim())} />
            <textarea className="input-field min-h-[72px]" value={argsText} onChange={(e) => setArgsText(e.target.value)} placeholder={"Args, one per line\n-y\n@modelcontextprotocol/server-filesystem"} disabled={Boolean(jsonText.trim())} />
            <textarea className="input-field min-h-[72px]" value={envText} onChange={(e) => setEnvText(e.target.value)} placeholder={"Env, one KEY=value per line"} disabled={Boolean(jsonText.trim())} />
          </>
        ) : (
          <>
            <input className="input-field" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://mcp.example.com/mcp" disabled={Boolean(jsonText.trim())} />
            <textarea className="input-field min-h-[72px]" value={headersText} onChange={(e) => setHeadersText(e.target.value)} placeholder={"Headers, one KEY=value per line\nAuthorization=Bearer ..."} disabled={Boolean(jsonText.trim())} />
          </>
        )}
        <textarea className="input-field min-h-[110px]" value={jsonText} onChange={(e) => setJsonText(e.target.value)} placeholder='{"mcpServers":{"server":{"transport":"stdio","command":"npx"}}}' />
        {jsonText.trim() && <div className="text-xs text-muted">{imported ? `JSON import ready: ${imported.name}` : "JSON import will be validated on save."}</div>}
        <div className="flex justify-end">
          <button type="button" className="h-8 px-3 rounded-md bg-ink text-on-ink text-sm disabled:opacity-[0.45]" disabled={busy === "save"} onClick={() => void save()}>
            {busy === "save" ? "Saving…" : "Save MCP server"}
          </button>
        </div>
      </section>

      <section className="grid gap-2">
        <div className="text-sm font-medium text-ink">3. Verify backend status</div>
        <button type="button" className="h-8 px-3 rounded-md border border-line bg-surface text-sm justify-self-start" disabled={busy === "refresh"} onClick={() => void refresh()}>
          {busy === "refresh" ? "Refreshing…" : "Refresh MCP status"}
        </button>
        {status && (
          <div className="rounded-[10px] border border-line-soft bg-surface-soft/35 px-3 py-2 text-xs text-muted grid gap-1">
            {status.mcp.servers.map((server) => (
              <div key={server.name}>
                {server.name}: {server.connected ? "connected" : "not connected"} · {server.tool_count} tools{server.error ? ` · ${server.error}` : ""}
                {server.auth === "oauth" && server.name === savedName && (
                  <button type="button" className="ml-2 underline text-ink-soft" onClick={() => void reauthenticate()}>Reauthenticate</button>
                )}
              </div>
            ))}
            {status.mcp.provider_statuses.map((provider) => <div key={provider.id}>{provider.label}: {provider.status} · {provider.tool_count} tools</div>)}
          </div>
        )}
        {saved && (
          <button type="button" className="h-8 px-3 rounded-md bg-ink text-on-ink text-sm justify-self-end" onClick={() => void onDone()}>
            Done
          </button>
        )}
      </section>
    </div>
  );
}
