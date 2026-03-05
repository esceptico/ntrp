import { colors, Hints } from "../../../ui/index.js";
import type { UseMCPServersResult } from "../../../../hooks/settings/useMCPServers.js";

interface MCPSectionProps {
  mcp: UseMCPServersResult;
  accent: string;
}

const LABEL_WIDTH = 14;

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

export function MCPSection({ mcp: m, accent }: MCPSectionProps) {
  return (
    <box flexDirection="column">
      {m.mcpServers.map((s, i) => {
        const selected = i === m.mcpIndex && !m.mcpAdding;
        return (
          <box key={s.name} flexDirection="column">
            <box flexDirection="row">
              <text>
                <span fg={selected ? accent : colors.text.disabled}>{selected ? "\u25B8 " : "  "}</span>
                <span fg={selected ? colors.text.primary : colors.text.secondary}>{s.name.padEnd(20)}</span>
              </text>
              <text>
                {s.connected ? (
                  <>
                    <span fg={colors.status.success}>{"\u2713 "}</span>
                    <span fg={colors.text.disabled}>{s.tool_count} tool{s.tool_count !== 1 ? "s" : ""}</span>
                    <span fg={colors.text.muted}>{" ("}{s.transport}{")"}</span>
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
            </box>
            {selected && s.error && (
              <box marginLeft={2}>
                <text><span fg={colors.status.error}>{"  "}{s.error}</span></text>
              </box>
            )}
            {selected && m.mcpConfirmRemove && (
              <box marginLeft={2}>
                <text><span fg={colors.status.warning}>{"  "}Remove {s.name}? (y/n)</span></text>
              </box>
            )}
          </box>
        );
      })}

      {m.mcpAdding && (
        <box flexDirection="column" marginTop={m.mcpServers.length > 0 ? 1 : 0}>
          <text><span fg={accent}>{"\u25B8 "}</span><span fg={accent}><strong>New Server</strong></span></text>

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
              <box flexDirection="row">
                <text>
                  <span fg={m.mcpAddField === "url" ? colors.text.primary : colors.text.secondary}>{"  URL".padEnd(LABEL_WIDTH)}</span>
                </text>
                {m.mcpAddField === "url" ? (
                  <TextInput value={m.mcpUrl} cursor={m.mcpUrlCursor} placeholder="http://localhost:8080/mcp" />
                ) : (
                  <text><span fg={m.mcpUrl ? colors.text.primary : colors.text.muted}>{m.mcpUrl || "..."}</span></text>
                )}
              </box>
            )}
          </box>
        </box>
      )}

      {m.mcpError && (
        <box marginTop={1}>
          <text><span fg={colors.status.error}>{"  "}{m.mcpError}</span></text>
        </box>
      )}

      {m.mcpSaving && (
        <box marginTop={1}>
          <text><span fg={colors.text.muted}>{"  "}Saving...</span></text>
        </box>
      )}

      {!m.mcpAdding && !m.mcpConfirmRemove && !m.mcpSaving && (
        <box marginTop={1} marginLeft={2}>
          {m.mcpServers.length > 0 && m.mcpServers[m.mcpIndex] ? (
            <Hints items={[["a", "add"], ["d", "remove"]]} />
          ) : (
            <Hints items={[["a", "add server"]]} />
          )}
        </box>
      )}

      {m.mcpAdding && !m.mcpSaving && (
        <box marginTop={1} marginLeft={2}>
          <Hints items={[["tab", "next"], ["^s", "save"], ["esc", "cancel"]]} />
        </box>
      )}
    </box>
  );
}
