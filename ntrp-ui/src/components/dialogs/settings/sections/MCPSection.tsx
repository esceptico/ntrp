import { colors } from "../../../ui/index.js";
import type { MCPServerInfo } from "../../../../api/client.js";

interface MCPSectionProps {
  servers: MCPServerInfo[];
  selectedIndex: number;
  accent: string;
  adding: boolean;
  addField: "name" | "transport" | "command" | "url";
  name: string;
  nameCursor: number;
  transport: "stdio" | "http";
  command: string;
  commandCursor: number;
  url: string;
  urlCursor: number;
  saving: boolean;
  error: string | null;
  confirmingRemove: boolean;
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

export function MCPSection({
  servers,
  selectedIndex,
  accent,
  adding,
  addField,
  name,
  nameCursor,
  transport,
  command,
  commandCursor,
  url,
  urlCursor,
  saving,
  error,
  confirmingRemove,
}: MCPSectionProps) {
  return (
    <box flexDirection="column">
      {servers.map((s, i) => {
        const selected = i === selectedIndex && !adding;
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
            {selected && confirmingRemove && (
              <box marginLeft={2}>
                <text><span fg={colors.status.warning}>{"  "}Remove {s.name}? (y/n)</span></text>
              </box>
            )}
          </box>
        );
      })}

      {adding && (
        <box flexDirection="column" marginTop={servers.length > 0 ? 1 : 0}>
          <text><span fg={accent}>{"\u25B8 "}</span><span fg={accent}><strong>New Server</strong></span></text>

          <box marginLeft={2} flexDirection="column">
            <box flexDirection="row">
              <text>
                <span fg={addField === "name" ? colors.text.primary : colors.text.secondary}>{"  Name".padEnd(LABEL_WIDTH)}</span>
              </text>
              {addField === "name" ? (
                <TextInput value={name} cursor={nameCursor} placeholder="server-name" />
              ) : (
                <text><span fg={name ? colors.text.primary : colors.text.muted}>{name || "..."}</span></text>
              )}
            </box>

            <box flexDirection="row">
              <text>
                <span fg={addField === "transport" ? colors.text.primary : colors.text.secondary}>{"  Transport".padEnd(LABEL_WIDTH)}</span>
              </text>
              <text>
                <span fg={transport === "stdio" ? accent : colors.text.disabled}>stdio</span>
                <span fg={colors.text.muted}>{" / "}</span>
                <span fg={transport === "http" ? accent : colors.text.disabled}>http</span>
                {addField === "transport" && <span fg={colors.text.muted}>{" (← → to switch)"}</span>}
              </text>
            </box>

            {transport === "stdio" ? (
              <box flexDirection="row">
                <text>
                  <span fg={addField === "command" ? colors.text.primary : colors.text.secondary}>{"  Command".padEnd(LABEL_WIDTH)}</span>
                </text>
                {addField === "command" ? (
                  <TextInput value={command} cursor={commandCursor} placeholder="npx -y @server/pkg" />
                ) : (
                  <text><span fg={command ? colors.text.primary : colors.text.muted}>{command || "..."}</span></text>
                )}
              </box>
            ) : (
              <box flexDirection="row">
                <text>
                  <span fg={addField === "url" ? colors.text.primary : colors.text.secondary}>{"  URL".padEnd(LABEL_WIDTH)}</span>
                </text>
                {addField === "url" ? (
                  <TextInput value={url} cursor={urlCursor} placeholder="http://localhost:8080/mcp" />
                ) : (
                  <text><span fg={url ? colors.text.primary : colors.text.muted}>{url || "..."}</span></text>
                )}
              </box>
            )}
          </box>
        </box>
      )}

      {error && (
        <box marginTop={1}>
          <text><span fg={colors.status.error}>{"  "}{error}</span></text>
        </box>
      )}

      {saving && (
        <box marginTop={1}>
          <text><span fg={colors.text.muted}>{"  "}Saving...</span></text>
        </box>
      )}

      {!adding && !confirmingRemove && !saving && (
        <box marginTop={1}>
          <text>
            <span fg={colors.text.disabled}>{"  "}</span>
            {servers.length > 0 && servers[selectedIndex] ? (
              <span fg={colors.text.disabled}>a add · d remove</span>
            ) : (
              <span fg={colors.text.disabled}>a add server</span>
            )}
          </text>
        </box>
      )}

      {adding && !saving && (
        <box marginTop={1}>
          <text><span fg={colors.text.disabled}>{"  "}tab next · ctrl+s save · esc cancel</span></text>
        </box>
      )}
    </box>
  );
}
