import { colors } from "../../../ui/index.js";
import type { ProviderInfo } from "../../../../api/client.js";

interface ProvidersSectionProps {
  providers: ProviderInfo[];
  selectedIndex: number;
  accent: string;
  editing: boolean;
  keyValue: string;
  keyCursor: number;
  saving: boolean;
  error: string | null;
  confirmingDisconnect: boolean;
}

export function ProvidersSection({
  providers,
  selectedIndex,
  accent,
  editing,
  keyValue,
  keyCursor,
  saving,
  error,
  confirmingDisconnect,
}: ProvidersSectionProps) {
  if (providers.length === 0) {
    return (
      <box flexDirection="column">
        <text><span fg={colors.text.muted}>  Loading...</span></text>
      </box>
    );
  }

  const provider = providers[selectedIndex];
  const maskedKey = keyValue ? "\u2022".repeat(Math.min(keyValue.length, 40)) : "";

  return (
    <box flexDirection="column">
      {providers.map((p, i) => {
        const selected = i === selectedIndex;
        const isCustom = p.id === "custom";
        const isEditing = selected && editing && !isCustom;

        return (
          <box key={p.id} flexDirection="column">
            <box flexDirection="row">
              <text>
                <span fg={selected ? accent : colors.text.disabled}>{selected ? "\u25B8 " : "  "}</span>
                <span fg={selected ? colors.text.primary : colors.text.secondary}>{p.name.padEnd(28)}</span>
              </text>
              {isCustom ? (
                <text>
                  <span fg={p.connected ? colors.status.success : colors.text.disabled}>
                    {p.model_count ? `${p.model_count} model${p.model_count !== 1 ? "s" : ""}` : "none"}
                  </span>
                </text>
              ) : (
                <text>
                  {p.connected ? (
                    <>
                      <span fg={colors.status.success}>{"\u2713 "}</span>
                      <span fg={colors.text.disabled}>{p.key_hint ?? ""}</span>
                      {p.from_env && <span fg={colors.text.muted}>{" (env)"}</span>}
                    </>
                  ) : (
                    <span fg={colors.text.disabled}>not connected</span>
                  )}
                </text>
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
                <text><span fg={colors.status.warning}>  Disconnect {p.name}? (y/n)</span></text>
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
            {provider && provider.id !== "custom" && provider.connected && !provider.from_env ? (
              <span fg={colors.text.disabled}>enter edit · d disconnect</span>
            ) : provider?.from_env ? (
              <span fg={colors.text.disabled}>set via environment variable</span>
            ) : provider?.id === "custom" ? (
              <span fg={colors.text.disabled}>use /connect to manage custom models</span>
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
