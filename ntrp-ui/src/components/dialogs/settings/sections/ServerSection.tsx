import { colors } from "../../../ui/index.js";
import { TextInputField } from "../../../ui/input/TextInputField.js";

interface ServerSectionProps {
  serverUrl: string;
  serverUrlCursor: number;
  apiKey: string;
  apiKeyCursor: number;
  selectedIndex: number;
  editing: boolean;
  accent: string;
  saving: boolean;
  error: string | null;
}

export function ServerSection({
  serverUrl,
  serverUrlCursor,
  apiKey,
  apiKeyCursor,
  selectedIndex,
  editing,
  accent,
  saving,
  error,
}: ServerSectionProps) {
  const maskedKey = apiKey ? "\u2022".repeat(Math.min(apiKey.length, 40)) : "";

  const items = [
    { label: "Server URL", value: serverUrl, cursor: serverUrlCursor, placeholder: "http://localhost:8000" },
    { label: "API Key", value: apiKey, displayValue: maskedKey, cursor: apiKeyCursor, placeholder: "your-api-key" },
  ];

  return (
    <box flexDirection="column">
      {items.map((item, i) => {
        const selected = i === selectedIndex;
        const isEditing = selected && editing;

        return (
          <box key={item.label} flexDirection="row">
            <text>
              <span fg={selected ? accent : colors.text.disabled}>{selected ? "▸ " : "  "}</span>
              <span fg={selected ? colors.text.primary : colors.text.secondary}>{item.label.padEnd(14)}</span>
            </text>
            {isEditing ? (
              <TextInputField
                value={i === 1 ? item.value : item.value}
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

      {saving && (
        <box marginTop={1}>
          <text><span fg={colors.text.muted}>  Saving...</span></text>
        </box>
      )}

      {error && (
        <box marginTop={1}>
          <text><span fg={colors.status.error}>  {error}</span></text>
        </box>
      )}

      {!editing && !saving && (
        <box marginTop={1}>
          <text><span fg={colors.text.disabled}>  enter to edit  </span></text>
        </box>
      )}

      {editing && (
        <box marginTop={1}>
          <text>
            <span fg={colors.text.disabled}>  tab to switch  ^s to save  esc to cancel</span>
          </text>
        </box>
      )}
    </box>
  );
}
