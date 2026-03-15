import { colors } from "../../../ui/index.js";
import { Row, FormField, StatusMessage } from "../SettingsRows.js";
import type { UseMCPServersResult } from "../../../../hooks/settings/useMCPServers.js";

interface MCPSectionProps {
  mcp: UseMCPServersResult;
  accent: string;
  width: number;
  height: number;
}

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
          return (
            <Row key={tool.name} selected={selected} accent={accent} arrow>
              <box width={2} flexShrink={0}>
                <text><span fg={enabled ? colors.status.success : colors.text.disabled}>{enabled ? "* " : "  "}</span></text>
              </box>
              <text><span fg={selected ? colors.text.primary : colors.text.secondary}>{clip(tool.name, maxName)}</span></text>
            </Row>
          );
        })}
      </box>
      {m.mcpError && <StatusMessage color={colors.status.error}>{m.mcpError}</StatusMessage>}
      {m.mcpSaving && <StatusMessage color={colors.text.muted}>Saving...</StatusMessage>}
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
            <Row selected={selected && !disabled} accent={accent} label={s.name} labelWidth={20} arrow>
              {disabled ? (
                <text><span fg={colors.text.disabled}>disabled</span></text>
              ) : s.connected ? (
                <text>
                  <span fg={colors.status.success}>{"\u2713 "}</span>
                  <span fg={colors.text.disabled}>{toolLabel}</span>
                  <span fg={colors.text.muted}>{" ("}{s.transport}{")"}</span>
                </text>
              ) : needsOAuth ? (
                <text>
                  <span fg={colors.status.warning}>{"\u25CB "}</span>
                  <span fg={colors.text.muted}>OAuth required</span>
                </text>
              ) : s.error ? (
                <text>
                  <span fg={colors.status.error}>{"\u2717 "}</span>
                  <span fg={colors.text.disabled}>{s.transport}</span>
                </text>
              ) : (
                <text><span fg={colors.text.disabled}>{s.transport}</span></text>
              )}
            </Row>
            {selected && s.error && (
              <box marginLeft={4}>
                <text><span fg={colors.status.error}>{clip(s.error, Math.max(6, width - 4))}</span></text>
              </box>
            )}
            {selected && m.mcpMode === "confirm-remove" && (
              <box marginLeft={4}>
                <text><span fg={colors.status.warning}>Remove {s.name}? (y/n)</span></text>
              </box>
            )}
            {selected && m.mcpMode === "oauth" && (
              <box marginLeft={4}>
                <text><span fg={colors.text.muted}>Authenticating in browser...</span></text>
              </box>
            )}
          </box>
        );
      })}

      {m.mcpMode === "add" && (
        <box flexDirection="column" marginTop={m.mcpServers.length > 0 ? 1 : 0}>
          <Row selected={true} accent={accent} arrow>
            <text><span fg={accent}><strong>New Server</strong></span></text>
          </Row>

          <box marginLeft={4} flexDirection="column">
            <FormField label="Name" active={m.mcpAddField === "name"}>
              {m.mcpAddField === "name" ? (
                <TextInput value={m.mcpName} cursor={m.mcpNameCursor} placeholder="server-name" />
              ) : (
                <text><span fg={m.mcpName ? colors.text.primary : colors.text.muted}>{m.mcpName || "..."}</span></text>
              )}
            </FormField>

            <FormField label="Transport" active={m.mcpAddField === "transport"}>
              <text>
                <span fg={m.mcpTransport === "stdio" ? accent : colors.text.disabled}>stdio</span>
                <span fg={colors.text.muted}>{" / "}</span>
                <span fg={m.mcpTransport === "http" ? accent : colors.text.disabled}>http</span>
                {m.mcpAddField === "transport" && <span fg={colors.text.muted}>{" (\u2190 \u2192 to switch)"}</span>}
              </text>
            </FormField>

            {m.mcpTransport === "stdio" ? (
              <FormField label="Command" active={m.mcpAddField === "command"}>
                {m.mcpAddField === "command" ? (
                  <TextInput value={m.mcpCommand} cursor={m.mcpCommandCursor} placeholder="npx -y @server/pkg" />
                ) : (
                  <text><span fg={m.mcpCommand ? colors.text.primary : colors.text.muted}>{m.mcpCommand || "..."}</span></text>
                )}
              </FormField>
            ) : (
              <>
                <FormField label="URL" active={m.mcpAddField === "url"}>
                  {m.mcpAddField === "url" ? (
                    <TextInput value={m.mcpUrl} cursor={m.mcpUrlCursor} placeholder="https://api.example.com/mcp" />
                  ) : (
                    <text><span fg={m.mcpUrl ? colors.text.primary : colors.text.muted}>{m.mcpUrl || "..."}</span></text>
                  )}
                </FormField>
                <FormField label="Auth" active={m.mcpAddField === "auth"}>
                  <text>
                    <span fg={m.mcpAuth === "none" ? accent : colors.text.disabled}>none</span>
                    <span fg={colors.text.muted}>{" / "}</span>
                    <span fg={m.mcpAuth === "oauth" ? accent : colors.text.disabled}>oauth</span>
                    {m.mcpAddField === "auth" && <span fg={colors.text.muted}>{" (\u2190 \u2192 to switch)"}</span>}
                  </text>
                </FormField>
                {m.mcpAuth !== "oauth" && (
                  <FormField label="Headers" active={m.mcpAddField === "headers"}>
                    {m.mcpAddField === "headers" ? (
                      <TextInput value={m.mcpHeaders} cursor={m.mcpHeadersCursor} placeholder="Authorization: Bearer token" />
                    ) : (
                      <text><span fg={m.mcpHeaders ? colors.text.primary : colors.text.muted}>{m.mcpHeaders || "(optional)"}</span></text>
                    )}
                  </FormField>
                )}
              </>
            )}
          </box>
        </box>
      )}

      {m.mcpError && m.mcpMode !== "tools" && <StatusMessage color={colors.status.error}>{m.mcpError}</StatusMessage>}
      {m.mcpSaving && <StatusMessage color={colors.text.muted}>Saving...</StatusMessage>}
    </box>
  );
}

export function MCPSection(props: MCPSectionProps) {
  if (props.mcp.mcpMode === "tools") {
    return <ToolFilter {...props} />;
  }
  return <ServerList {...props} />;
}
