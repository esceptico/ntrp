import { useEffect, useMemo, useState } from "react";
import { fetchServerConfig, updateServerConfig } from "../../actions";
import { listToolsApi, type ToolMetadata, type ToolOverrideDecision } from "../../api";
import { useStore } from "../../store";
import { useMutationState } from "../../lib/hooks";
import { settingsErrorMessage } from "../../lib/settingsLoadState";
import { SettingsConnectionHint, SettingsInlineError } from "./SettingsNotice";
import { GlassToggle } from "../GlassToggle";

const DECISIONS: Array<{ value: ToolOverrideDecision; label: string }> = [
  { value: "approve", label: "Approve" },
  { value: "ask", label: "Ask" },
  { value: "deny", label: "Deny" },
];

export function ToolsTab() {
  const config = useStore((s) => s.config);
  const serverConfig = useStore((s) => s.serverConfig);
  const { error, run } = useMutationState();
  const [tools, setTools] = useState<ToolMetadata[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  async function refresh() {
    setLoadError(null);
    try {
      const r = await listToolsApi(config);
      setTools(r.tools);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : String(err));
      setTools([]);
    }
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const overrides = serverConfig?.tool_overrides ?? {};
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const list = (tools ?? []).filter((tool) => tool.source !== "mcp");
    if (!needle) return list;
    return list.filter((tool) =>
      [tool.name, tool.display_name, tool.description, tool.source ?? ""]
        .join(" ")
        .toLowerCase()
        .includes(needle),
    );
  }, [query, tools]);

  const groups = useMemo(() => {
    const out = new Map<string, ToolMetadata[]>();
    for (const tool of filtered) {
      const source = tool.source || "unknown";
      if (!out.has(source)) out.set(source, []);
      out.get(source)!.push(tool);
    }
    return Array.from(out.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [filtered]);

  function baseDecision(tool: ToolMetadata): ToolOverrideDecision {
    return tool.policy.requires_approval ? "ask" : "approve";
  }

  function setOverride(tool: ToolMetadata, decision: ToolOverrideDecision) {
    const next = { ...overrides };
    if (decision === baseDecision(tool)) delete next[tool.name];
    else next[tool.name] = decision;
    void run(async () => {
      await updateServerConfig({ tool_overrides: next });
      await fetchServerConfig();
      await refresh();
    });
  }

  if (tools === null) {
    return <div className="text-sm text-faint">Loading tools…</div>;
  }

  if (loadError) {
    return (
      <div className="grid gap-3">
        <SettingsInlineError title="Couldn't load tools" message={settingsErrorMessage(loadError)} />
        <SettingsConnectionHint />
      </div>
    );
  }

  return (
    <div className="grid gap-4">
      <div className="flex items-center justify-between gap-3">
        <p className="m-0 text-sm text-muted leading-[1.45] max-w-[520px]">
          Override tool approval behavior. Denied tools are hidden from the agent and blocked at execution.
        </p>
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search tools"
          spellCheck={false}
          className="w-[220px] h-8 px-2.5 rounded-md border border-line-soft bg-surface text-sm text-ink outline-none focus:border-line transition-colors"
        />
      </div>

      {error && <SettingsInlineError title="Couldn't save tool override" message={error} />}

      <div className="grid gap-3">
        {groups.map(([source, items]) => (
          <section key={source} className="grid gap-2">
            <h3 className="m-0 text-xs font-medium uppercase tracking-[0.06em] text-faint">
              {formatSource(source)} ({items.length})
            </h3>
            <ul className="rounded-[10px] border border-line-soft bg-bg-main/30 divide-y divide-line-soft m-0 p-0 list-none">
              {items.map((tool) => {
                const current = overrides[tool.name] ?? baseDecision(tool);
                return (
                  <li key={tool.name} className="grid grid-cols-[minmax(0,1fr)_auto] gap-3 px-3 py-2.5">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="text-sm font-medium text-ink truncate">{tool.display_name}</span>
                        <span className="text-2xs uppercase tracking-[0.06em] text-faint shrink-0">
                          {tool.policy.action}
                        </span>
                      </div>
                      <div className="mt-0.5 text-xs text-faint font-mono truncate">{tool.name}</div>
                      {tool.description && (
                        <div className="mt-1 text-xs text-muted leading-snug line-clamp-2">
                          {tool.description}
                        </div>
                      )}
                    </div>
                    <GlassToggle
                      size="sm"
                      options={DECISIONS}
                      value={current}
                      onChange={(v) => setOverride(tool, v as ToolOverrideDecision)}
                    />
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}

function formatSource(source: string): string {
  return source.replace(/^_+/, "").replaceAll("_", " ");
}
