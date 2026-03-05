import { colors, Hints } from "../../../ui/index.js";
import type { UseMCPServersResult } from "../../../../hooks/settings/useMCPServers.js";

interface MCPSectionProps {
  mcp: UseMCPServersResult;
  accent: string;
  width: number;
  height: number;
}

const LABEL_WIDTH = 14;

function clip(str: string, max: number): string {
  if (max < 4) return str.slice(0, max);
  return str.length <= max ? str : str.slice(0, max - 1) + "\u2026";
}

function TextInput({ value, cursor, placeholder }: { value: string; cursor: number; placeholder?: string }) {
  if (!value && placeholder) {
    return (
      <text>
        <span fg={colors.text.muted}>{placeholder}</span>
        <span bg={colors.text.primary} fg={colors.contrast}>{" "}</span>
      </text>
    );
  }
  return (
    <text>
      <span fg={colors.text.primary}>{value.slice(0, cursor)}</span>
      <span bg={colors.text.primary} fg={colors.contrast}>{value[cursor] || " "}</span>
      <span fg={colors.text.primary}>{value.slice(cursor + 1)}</span>
    </text>
  );
}

function ToolFilter({ mcp: m, accent, width, height }: MCPSectionProps) {
  const server = m.mcpServers[m.mcpIndex];
  if (!server) return null;
  const tools = server.tools ?? [];
  const enabledCount = m.mcpToolEnabled.filter(Boolean).length;
  const maxName = Math.max(6, width - 6);

  // Header = 1 line + 1 margin, reserve 1 for status. Each tool = 1 line.
  const visibleCount = Math.max(1, height - 3);
  const maxStart = Math.max(0, tools.length - visibleCount);
  const scrollStart = Math.min(maxStart, Math.max(0, m.mcpToolIndex - visibleCount + 1));
  const visibleTools = tools.slice(scrollStart, scrollStart + visibleCount);

  return (
    <box flexDirection="column">
      <text>
        <span fg={accent}><strong>{server.name}</strong></span>
        <span fg={colors.text.muted}>{" \u2014 "}{enabledCount}/{tools.length} enabled</span>
      </text>
      <box flexDirection="column" marginTop={1}>
        {visibleTools.map((tool, vi) => {
          const i = scrollStart + vi;
          const selected = i === m.mcpToolIndex;
          const enabled = m.mcpToolEnabled[i] ?? true;
          const arrow = selected ? "> " : "  ";
          const check = enabled ? "* " : "  ";
          const name = clip(tool.name, maxName);
          return (
            <text key={tool.name}>
              <span fg={selected ? accent : colors.text.disabled}>{arrow}</span>
              <span fg={enabled ? colors.status.success : colors.text.disabled}>{check}</span>
              <span fg={selected ? colors.text.primary : colors.text.secondary}>{name}</span>
            </text>
          );
        })}
      </box>
      {m.mcpError && (
        <text><span fg={colors.status.error}>{"  "}{m.mcpError}</span></text>
      )}
      {m.mcpSaving && (
        <text><span fg={colors.text.muted}>{"  "}Saving...</span></text>
      )}
    </box>
  );
}

function ServerList({ mcp: m, accent, width }: MCPSectionProps) {
  return (
    <box flexDirection="column">
      {m.mcpServers.map((s, i) => {
        const selected = i === m.mcpIndex && (m.mcpMode === "list" || m.mcpMode === "confirm-remove" || m.mcpMode === "oauth");
        const disabled = !s.enabled;
        const totalTools = (s.tools ?? []).length;
        const toolLabel = s.tool_count === totalTools
          ? `${s.tool_count} tool${s.tool_count !== 1 ? "s" : ""}`
          : `${s.tool_count}/${totalTools} tools`;
        const needsOAuth = s.auth === "oauth" && !s.connected && s.enabled;
        return (
          <box key={s.name} flexDirection="column">
            <text>
              <span fg={selected ? accent : colors.text.disabled}>{selected ? "> " : "  "}</span>
              <span fg={disabled ? colors.text.disabled : selected ? colors.text.primary : colors.text.secondary}>{s.name.padEnd(20)}</span>
              {disabled ? (
                <span fg={colors.text.disabled}>disabled</span>
              ) : s.connected ? (
                <>
                  <span fg={colors.status.success}>{"\u2713 "}</span>
                  <span fg={colors.text.disabled}>{toolLabel}</span>
                  <span fg={colors.text.muted}>{" ("}{s.transport}{")"}</span>
                </>
              ) : needsOAuth ? (
                <>
                  <span fg={colors.status.warning}>{"\u25CB "}</span>
                  <span fg={colors.text.muted}>OAuth required</span>
                </>
              ) : s.error ? (
                <>
                  <span fg={colors.status.error}>{"\u2717 "}</span>
                  <span fg={colors.text.disabled}>{s.transport}</span>
                </>
              ) : (
                <span fg={colors.text.disabled}>{s.transport}</span>
              )}
            </text>
            {selected && s.error && (
              <text>
                <span fg={colors.status.error}>{"    "}{clip(s.error, Math.max(6, width - 4))}</span>
              </text>
            )}
            {selected && m.mcpMode === "confirm-remove" && (
              <text>
                <span fg={colors.status.warning}>{"    "}Remove {s.name}? (y/n)</span>
              </text>
            )}
            {selected && m.mcpMode === "oauth" && (
              <text>
                <span fg={colors.text.muted}>{"    "}Authenticating in browser...</span>
              </text>
            )}
          </box>
        );
      })}

      {m.mcpMode === "add" && (
        <box flexDirection="column" marginTop={m.mcpServers.length > 0 ? 1 : 0}>
          <text><span fg={accent}>{"> "}</span><span fg={accent}><strong>New Server</strong></span></text>

          <box marginLeft={2} flexDirection="column">
            <box flexDirection="row">
              <text>
                <span fg={m.mcpAddField === "name" ? colors.text.primary : colors.text.secondary}>{"  Name".padEnd(LABEL_WIDTH)}</span>
              </text>
              {m.mcpAddField === "name" ? (
                <TextInput value={m.mcpName} cursor={m.mcpNameCursor} placeholder="server-name" />
              ) : (
                <text><span fg={m.mcpName ? colors.text.primary : colors.text.muted}>{m.mcpName || "..."}</span></text>
              )}
            </box>

            <box flexDirection="row">
              <text>
                <span fg={m.mcpAddField === "transport" ? colors.text.primary : colors.text.secondary}>{"  Transport".padEnd(LABEL_WIDTH)}</span>
              </text>
              <text>
                <span fg={m.mcpTransport === "stdio" ? accent : colors.text.disabled}>stdio</span>
                <span fg={colors.text.muted}>{" / "}</span>
                <span fg={m.mcpTransport === "http" ? accent : colors.text.disabled}>http</span>
                {m.mcpAddField === "transport" && <span fg={colors.text.muted}>{" (\u2190 \u2192 to switch)"}</span>}
              </text>
            </box>

            {m.mcpTransport === "stdio" ? (
              <box flexDirection="row">
                <text>
                  <span fg={m.mcpAddField === "command" ? colors.text.primary : colors.text.secondary}>{"  Command".padEnd(LABEL_WIDTH)}</span>
                </text>
                {m.mcpAddField === "command" ? (
                  <TextInput value={m.mcpCommand} cursor={m.mcpCommandCursor} placeholder="npx -y @server/pkg" />
                ) : (
                  <text><span fg={m.mcpCommand ? colors.text.primary : colors.text.muted}>{m.mcpCommand || "..."}</span></text>
                )}
              </box>
            ) : (
              <>
                <box flexDirection="row">
                  <text>
                    <span fg={m.mcpAddField === "url" ? colors.text.primary : colors.text.secondary}>{"  URL".padEnd(LABEL_WIDTH)}</span>
                  </text>
                  {m.mcpAddField === "url" ? (
                    <TextInput value={m.mcpUrl} cursor={m.mcpUrlCursor} placeholder="https://api.example.com/mcp" />
                  ) : (
                    <text><span fg={m.mcpUrl ? colors.text.primary : colors.text.muted}>{m.mcpUrl || "..."}</span></text>
                  )}
                </box>
                <box flexDirection="row">
                  <text>
                    <span fg={m.mcpAddField === "auth" ? colors.text.primary : colors.text.secondary}>{"  Auth".padEnd(LABEL_WIDTH)}</span>
                  </text>
                  <text>
                    <span fg={m.mcpAuth === "none" ? accent : colors.text.disabled}>none</span>
                    <span fg={colors.text.muted}>{" / "}</span>
                    <span fg={m.mcpAuth === "oauth" ? accent : colors.text.disabled}>oauth</span>
                    {m.mcpAddField === "auth" && <span fg={colors.text.muted}>{" (\u2190 \u2192 to switch)"}</span>}
                  </text>
                </box>
                {m.mcpAuth !== "oauth" && (
                  <box flexDirection="row">
                    <text>
                      <span fg={m.mcpAddField === "headers" ? colors.text.primary : colors.text.secondary}>{"  Headers".padEnd(LABEL_WIDTH)}</span>
                    </text>
                    {m.mcpAddField === "headers" ? (
                      <TextInput value={m.mcpHeaders} cursor={m.mcpHeadersCursor} placeholder="Authorization: Bearer token" />
                    ) : (
                      <text><span fg={m.mcpHeaders ? colors.text.primary : colors.text.muted}>{m.mcpHeaders || "(optional)"}</span></text>
                    )}
                  </box>
                )}
              </>
            )}
          </box>
        </box>
      )}

      {m.mcpError && m.mcpMode !== "tools" && (
        <box marginTop={1}>
          <text><span fg={colors.status.error}>{"  "}{m.mcpError}</span></text>
        </box>
      )}

      {m.mcpSaving && (
        <box marginTop={1}>
          <text><span fg={colors.text.muted}>{"  "}Saving...</span></text>
        </box>
      )}

      {m.mcpMode === "list" && !m.mcpSaving && (
        <box marginTop={1} marginLeft={2}>
          {m.mcpServers.length > 0 && m.mcpServers[m.mcpIndex] ? (() => {
            const s = m.mcpServers[m.mcpIndex]!;
            const hints: [string, string][] = [];
            if (s.connected) hints.push(["enter", "tools"]);
            hints.push(["a", "add"]);
            hints.push(["e", s.enabled ? "disable" : "enable"]);
            if (s.auth === "oauth" && s.enabled) hints.push(["o", "oauth"]);
            hints.push(["d", "remove"]);
            return <Hints items={hints} />;
          })() : (
            <Hints items={[["a", "add server"]]} />
          )}
        </box>
      )}

      {m.mcpMode === "add" && !m.mcpSaving && (
        <box marginTop={1} marginLeft={2}>
          <Hints items={[["tab", "next"], ["^s", "save"], ["esc", "cancel"]]} />
        </box>
      )}
    </box>
  );
}

export function MCPSection(props: MCPSectionProps) {
  if (props.mcp.mcpMode === "tools") {
    return <ToolFilter {...props} />;
  }
  return <ServerList {...props} />;
}
