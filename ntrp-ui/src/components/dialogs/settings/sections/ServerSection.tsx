import { colors, Hints } from "../../../ui/index.js";
import { TextInputField } from "../../../ui/input/TextInputField.js";
import type { UseServerConnectionResult } from "../../../../hooks/settings/useServerConnection.js";

interface ServerSectionProps {
  server: UseServerConnectionResult;
  accent: string;
}

export function ServerSection({ server: s, accent }: ServerSectionProps) {
  const maskedKey = s.serverApiKey ? "\u2022".repeat(Math.min(s.serverApiKey.length, 40)) : "";

  const items = [
    { label: "Server URL", value: s.serverUrl, cursor: s.serverUrlCursor, placeholder: "http://localhost:6877" },
    { label: "API Key", value: s.serverApiKey, displayValue: maskedKey, cursor: s.serverApiKeyCursor, placeholder: "your-api-key" },
  ];

  return (
    <box flexDirection="column">
      {items.map((item, i) => {
        const selected = i === s.serverIndex;
        const isEditing = selected && s.editingServer;

        return (
          <box key={item.label} flexDirection="row">
            <text>
              <span fg={selected ? accent : colors.text.disabled}>{selected ? "▸ " : "  "}</span>
              <span fg={selected ? colors.text.primary : colors.text.secondary}>{item.label.padEnd(14)}</span>
            </text>
            {isEditing ? (
              <TextInputField
                value={item.value}
                cursorPos={item.cursor}
                placeholder={item.placeholder}
              />
            ) : (
              <text>
                <span fg={colors.text.muted}>{item.displayValue ?? (item.value || item.placeholder)}</span>
              </text>
            )}
          </box>
        );
      })}

      <box flexDirection="row">
        <text>
          <span fg={s.serverIndex === 2 ? accent : colors.text.disabled}>{s.serverIndex === 2 ? "▸ " : "  "}</span>
          <span fg={s.streaming ? (s.serverIndex === 2 ? accent : colors.text.primary) : colors.text.muted}>
            {s.streaming ? "\u25CF" : "\u25CB"}
          </span>
          <span fg={s.serverIndex === 2 ? colors.text.primary : colors.text.secondary}> Streaming</span>
        </text>
      </box>

      {s.serverSaving && (
        <box marginTop={1}>
          <text><span fg={colors.text.muted}>  Saving...</span></text>
        </box>
      )}

      {s.serverError && (
        <box marginTop={1}>
          <text><span fg={colors.status.error}>  {s.serverError}</span></text>
        </box>
      )}

      {!s.editingServer && !s.serverSaving && (
        <box marginTop={1} marginLeft={2}>
          <Hints items={[["enter", "edit"]]} />
        </box>
      )}

      {s.editingServer && (
        <box marginTop={1} marginLeft={2}>
          <Hints items={[["tab", "switch"], ["^s", "save"], ["esc", "cancel"]]} />
        </box>
      )}
    </box>
  );
}
