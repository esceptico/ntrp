import { colors } from "../../../ui/colors.js";
import { TextInputField } from "../../../ui/input/TextInputField.js";
import { Row, StatusMessage } from "../SettingsRows.js";
import type { UseServerConnectionResult } from "../../../../hooks/settings/useServerConnection.js";

interface ConnectionSectionProps {
  server: UseServerConnectionResult;
  accent: string;
}

export function ConnectionSection({ server: s, accent }: ConnectionSectionProps) {
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
          <Row key={item.label} selected={selected} accent={accent} label={item.label} labelWidth={14}>
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
          </Row>
        );
      })}

      {s.serverSaving && <StatusMessage color={colors.text.muted}>Saving...</StatusMessage>}
      {s.serverError && <StatusMessage color={colors.status.error}>{s.serverError}</StatusMessage>}
    </box>
  );
}
