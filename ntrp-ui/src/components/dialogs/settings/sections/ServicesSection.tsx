import { colors } from "../../../ui/index.js";
import type { ServiceInfo } from "../../../../api/client.js";

interface ServicesSectionProps {
  services: ServiceInfo[];
  selectedIndex: number;
  accent: string;
  editing: boolean;
  keyValue: string;
  keyCursor: number;
  saving: boolean;
  error: string | null;
  confirmingDisconnect: boolean;
}

export function ServicesSection({
  services,
  selectedIndex,
  accent,
  editing,
  keyValue,
  keyCursor,
  saving,
  error,
  confirmingDisconnect,
}: ServicesSectionProps) {
  if (services.length === 0) {
    return (
      <box flexDirection="column">
        <text><span fg={colors.text.muted}>  Loading...</span></text>
      </box>
    );
  }

  const service = services[selectedIndex];
  const maskedKey = keyValue ? "\u2022".repeat(Math.min(keyValue.length, 40)) : "";

  return (
    <box flexDirection="column">
      {services.map((s, i) => {
        const selected = i === selectedIndex;
        const isEditing = selected && editing;

        return (
          <box key={s.id} flexDirection="column">
            <box flexDirection="row">
              <text>
                <span fg={selected ? accent : colors.text.disabled}>{selected ? "\u25B8 " : "  "}</span>
                <span fg={selected ? colors.text.primary : colors.text.secondary}>{s.name.padEnd(24)}</span>
              </text>
              {s.connected ? (
                <text>
                  <span fg={colors.status.success}>{"\u2713 "}</span>
                  <span fg={colors.text.disabled}>{s.key_hint ?? ""}</span>
                  {s.from_env && <span fg={colors.text.muted}>{" (env)"}</span>}
                </text>
              ) : (
                <text><span fg={colors.text.disabled}>not connected</span></text>
              )}
            </box>
            {isEditing && (
              <box marginLeft={2}>
                <box flexDirection="row">
                  <text><span fg={colors.text.primary}>{"  API Key".padEnd(14)}</span></text>
                  {keyValue ? (
                    <text>
                      <span fg={colors.text.primary}>{maskedKey.slice(0, keyCursor)}</span>
                      <span bg={colors.text.primary} fg={colors.contrast}>{maskedKey[keyCursor] || " "}</span>
                      <span fg={colors.text.primary}>{maskedKey.slice(keyCursor + 1)}</span>
                    </text>
                  ) : (
                    <text>
                      <span fg={colors.text.muted}>paste key...</span>
                      <span bg={colors.text.primary} fg={colors.contrast}>{" "}</span>
                    </text>
                  )}
                </box>
              </box>
            )}
            {selected && confirmingDisconnect && (
              <box marginLeft={2}>
                <text><span fg={colors.status.warning}>  Disconnect {s.name}? (y/n)</span></text>
              </box>
            )}
          </box>
        );
      })}

      {error && (
        <box marginTop={1}>
          <text><span fg={colors.status.error}>  {error}</span></text>
        </box>
      )}

      {saving && (
        <box marginTop={1}>
          <text><span fg={colors.text.muted}>  Saving...</span></text>
        </box>
      )}

      {!editing && !confirmingDisconnect && !saving && (
        <box marginTop={1}>
          <text>
            <span fg={colors.text.disabled}>  </span>
            {service?.connected && !service.from_env ? (
              <span fg={colors.text.disabled}>enter edit · d disconnect</span>
            ) : service?.from_env ? (
              <span fg={colors.text.disabled}>set via environment variable</span>
            ) : (
              <span fg={colors.text.disabled}>enter to add key</span>
            )}
          </text>
        </box>
      )}

      {editing && (
        <box marginTop={1}>
          <text><span fg={colors.text.disabled}>  enter to save · esc to cancel</span></text>
        </box>
      )}
    </box>
  );
}
