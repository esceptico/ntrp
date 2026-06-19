import { useMemo } from "react";
import { useStore } from "../../../store";
import { type MCPServer, type ToolOverrideDecision, updateMCPToolsApi } from "../../../api";
import { fetchServerConfig, updateServerConfig } from "../../../actions";
import { useMutationState } from "../../../lib/hooks";
import { SettingsInlineError } from "../SettingsNotice";
import { SegmentedControl, SegmentedControlItem } from "../../SegmentedControl";
import { SwitchControl } from "../../SwitchControl";
import { SectionHeader } from "../../SectionHeader";

const TOOL_DECISIONS: Array<{ value: ToolOverrideDecision; label: string }> = [
  { value: "approve", label: "Approve" },
  { value: "ask", label: "Ask" },
  { value: "deny", label: "Deny" },
];

export function ToolsSection({
  server,
  onChanged,
}: {
  server: MCPServer;
  onChanged: () => Promise<void>;
}) {
  const config = useStore((s) => s.config);
  const serverConfig = useStore((s) => s.serverConfig);
  const { busy, error, run } = useMutationState();
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
      <SectionHeader label="Tools" count={server.tools.length} />
      <ul className="rounded-md border border-line-soft bg-bg-main/30 divide-y divide-line-soft m-0 p-0 list-none">
        {server.tools.map((t) => {
          const checked = enabledNames.has(t.name);
          return (
            <li key={t.name} className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-start gap-3 px-3 py-2">
              <SwitchControl
                size="sm"
                checked={checked}
                disabled={busy}
                onChange={(next) => {
                  const updated = new Set(enabledNames);
                  if (next) updated.add(t.name);
                  else updated.delete(t.name);
                  commit(updated);
                }}
                aria-label={`Include ${t.name}`}
                className="mt-[3px]"
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
              <SegmentedControl
                size="sm"
                value={overrides[t.full_name] ?? baseDecision(t)}
                onChange={(v) => setToolDecision(t, v as ToolOverrideDecision)}
              >
                {TOOL_DECISIONS.map((d) => (
                  <SegmentedControlItem key={d.value} value={d.value}>
                    {d.label}
                  </SegmentedControlItem>
                ))}
              </SegmentedControl>
            </li>
          );
        })}
      </ul>
      {error && <SettingsInlineError title="Couldn't update tools" message={error} />}
    </div>
  );
}
