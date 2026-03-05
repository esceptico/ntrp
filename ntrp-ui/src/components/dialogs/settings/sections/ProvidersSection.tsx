import { colors, Hints } from "../../../ui/index.js";
import type { ProviderInfo } from "../../../../api/client.js";
import type { UseCredentialSectionResult } from "../../../../hooks/settings/useCredentialSection.js";
import { MaskedKeyInput } from "./shared.js";

interface ProvidersSectionProps {
  providers: UseCredentialSectionResult<ProviderInfo>;
  accent: string;
}

export function ProvidersSection({ providers: s, accent }: ProvidersSectionProps) {
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
      {s.items.map((provider, i) => {
        const selected = i === s.selectedIndex;
        const isCustom = provider.id === "custom";
        const isEditing = selected && s.editing && !isCustom;

        return (
          <box key={provider.id} flexDirection="column">
            <box flexDirection="row">
              <text>
                <span fg={selected ? accent : colors.text.disabled}>{selected ? "\u25B8 " : "  "}</span>
                <span fg={selected ? colors.text.primary : colors.text.secondary}>{provider.name.padEnd(28)}</span>
              </text>
              {isCustom ? (
                <text>
                  <span fg={provider.connected ? colors.status.success : colors.text.disabled}>
                    {provider.model_count ? `${provider.model_count} model${provider.model_count !== 1 ? "s" : ""}` : "none"}
                  </span>
                </text>
              ) : (
                <text>
                  {provider.connected ? (
                    <>
                      <span fg={colors.status.success}>{"\u2713 "}</span>
                      <span fg={colors.text.disabled}>{provider.key_hint ?? ""}</span>
                      {provider.from_env && <span fg={colors.text.muted}>{" (env)"}</span>}
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
                  <MaskedKeyInput value={s.keyValue} cursor={s.keyCursor} />
                </box>
              </box>
            )}
            {selected && s.confirmDisconnect && (
              <box marginLeft={2}>
                <text><span fg={colors.status.warning}>  Disconnect {provider.name}? (y/n)</span></text>
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

      {!s.editing && !s.confirmDisconnect && !s.saving && (
        <box marginTop={1} marginLeft={2}>
          {current && current.id !== "custom" && current.connected && !current.from_env ? (
            <Hints items={[["enter", "edit"], ["d", "disconnect"]]} />
          ) : current?.from_env ? (
            <text><span fg={colors.text.disabled}>set via environment variable</span></text>
          ) : current?.id === "custom" ? (
            <text><span fg={colors.text.disabled}>use /connect to manage custom models</span></text>
          ) : (
            <Hints items={[["enter", "add key"]]} />
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
