import { colors } from "../../../ui/index.js";
import { Row, StatusMessage, FormField } from "../SettingsRows.js";
import type { UseCredentialSectionResult } from "../../../../hooks/settings/useCredentialSection.js";
import { MaskedKeyInput } from "./shared.js";

interface CredentialItem {
  id: string;
  name: string;
  connected: boolean;
  key_hint?: string | null;
  from_env?: boolean;
  auth_type?: "api_key" | "oauth";
}

interface CredentialSectionProps<T extends CredentialItem> {
  state: UseCredentialSectionResult<T>;
  accent: string;
  labelWidth?: number;
  renderStatus?: (item: T, selected: boolean) => React.ReactNode;
  isEditable?: (item: T) => boolean;
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
  if (item.auth_type === "oauth") {
    return <text><span fg={colors.text.disabled}>press enter to sign in</span></text>;
  }
  return <text><span fg={colors.text.disabled}>not connected</span></text>;
}

export function CredentialSection<T extends CredentialItem>({
  state: s,
  accent,
  labelWidth = 24,
  renderStatus,
  isEditable,
}: CredentialSectionProps<T>) {
  if (s.items.length === 0) {
    return <StatusMessage color={colors.text.muted}>Loading...</StatusMessage>;
  }

  return (
    <box flexDirection="column">
      {s.items.map((item, i) => {
        const selected = i === s.selectedIndex;
        const canEdit = isEditable ? isEditable(item) : true;
        const isEditing = selected && s.editing && canEdit;

        return (
          <box key={item.id} flexDirection="column">
            <Row selected={selected} accent={accent} label={item.name} labelWidth={labelWidth}>
              {renderStatus ? renderStatus(item, selected) : <DefaultStatus item={item} />}
            </Row>
            {isEditing && (
              <box marginLeft={4}>
                <FormField label="API Key" active={true}>
                  <MaskedKeyInput value={s.keyValue} cursor={s.keyCursor} />
                </FormField>
              </box>
            )}
            {selected && s.confirmDisconnect && (
              <box marginLeft={4}>
                <text><span fg={colors.status.warning}>Disconnect {item.name}? (y/n)</span></text>
              </box>
            )}
            {selected && item.auth_type === "oauth" && s.oauthPendingId === item.id && (
              <box marginLeft={4} flexDirection="column">
                {s.notice && <text><span fg={colors.status.warning}>{s.notice}</span></text>}
                {s.oauthUrl && <text><span fg={colors.text.disabled}>{s.oauthUrl}</span></text>}
              </box>
            )}
          </box>
        );
      })}

      {s.error && <StatusMessage color={colors.status.error}>{s.error}</StatusMessage>}
      {s.notice && !s.oauthPendingId && <StatusMessage color={colors.text.muted}>{s.notice}</StatusMessage>}
      {s.saving && <StatusMessage color={colors.text.muted}>Saving...</StatusMessage>}
    </box>
  );
}
