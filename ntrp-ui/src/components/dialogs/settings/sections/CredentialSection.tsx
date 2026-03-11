import { colors, Hints } from "../../../ui/index.js";
import type { UseCredentialSectionResult } from "../../../../hooks/settings/useCredentialSection.js";
import { MaskedKeyInput } from "./shared.js";

interface CredentialItem {
  id: string;
  name: string;
  connected: boolean;
  key_hint?: string | null;
  from_env?: boolean;
}

interface CredentialSectionProps<T extends CredentialItem> {
  state: UseCredentialSectionResult<T>;
  accent: string;
  labelWidth?: number;
  renderStatus?: (item: T, selected: boolean) => React.ReactNode;
  renderHints?: (item: T) => React.ReactNode;
  isEditable?: (item: T) => boolean;
  suppressHints?: boolean;
}

function DefaultStatus({ item }: { item: CredentialItem }) {
  if (item.connected) {
    return (
      <text>
        <span fg={colors.status.success}>{"\u2713 "}</span>
        <span fg={colors.text.disabled}>{item.key_hint ?? ""}</span>
        {item.from_env && <span fg={colors.text.muted}>{" (env)"}</span>}
      </text>
    );
  }
  return <text><span fg={colors.text.disabled}>not connected</span></text>;
}

export function CredentialSection<T extends CredentialItem>({
  state: s,
  accent,
  labelWidth = 24,
  renderStatus,
  renderHints,
  isEditable,
  suppressHints,
}: CredentialSectionProps<T>) {
  if (s.items.length === 0) {
    return (
      <box flexDirection="column">
        <text><span fg={colors.text.muted}>  Loading...</span></text>
      </box>
    );
  }

  const current = s.items[s.selectedIndex];

  return (
    <box flexDirection="column">
      {s.items.map((item, i) => {
        const selected = i === s.selectedIndex;
        const canEdit = isEditable ? isEditable(item) : true;
        const isEditing = selected && s.editing && canEdit;

        return (
          <box key={item.id} flexDirection="column">
            <box flexDirection="row">
              <text>
                <span fg={selected ? accent : colors.text.disabled}>{selected ? "\u25B8 " : "  "}</span>
                <span fg={selected ? colors.text.primary : colors.text.secondary}>{item.name.padEnd(labelWidth)}</span>
              </text>
              {renderStatus ? renderStatus(item, selected) : <DefaultStatus item={item} />}
            </box>
            {isEditing && (
              <box marginLeft={2}>
                <box flexDirection="row">
                  <text><span fg={colors.text.primary}>{"  API Key".padEnd(14)}</span></text>
                  <MaskedKeyInput value={s.keyValue} cursor={s.keyCursor} />
                </box>
              </box>
            )}
            {selected && s.confirmDisconnect && (
              <box marginLeft={2}>
                <text><span fg={colors.status.warning}>  Disconnect {item.name}? (y/n)</span></text>
              </box>
            )}
          </box>
        );
      })}

      {s.error && (
        <box marginTop={1}>
          <text><span fg={colors.status.error}>  {s.error}</span></text>
        </box>
      )}

      {s.saving && (
        <box marginTop={1}>
          <text><span fg={colors.text.muted}>  Saving...</span></text>
        </box>
      )}

      {!s.editing && !s.confirmDisconnect && !s.saving && !suppressHints && (
        <box marginTop={1} marginLeft={2}>
          {renderHints?.(current) ?? (
            current?.connected && !current.from_env ? (
              <Hints items={[["enter", "edit"], ["d", "disconnect"]]} />
            ) : current?.from_env ? (
              <text><span fg={colors.text.disabled}>set via environment variable</span></text>
            ) : (
              <Hints items={[["enter", "add key"]]} />
            )
          )}
        </box>
      )}

      {s.editing && (
        <box marginTop={1} marginLeft={2}>
          <Hints items={[["enter", "save"], ["esc", "cancel"]]} />
        </box>
      )}
    </box>
  );
}
