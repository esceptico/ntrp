import { colors, Hints } from "../../../ui/index.js";
import type { UseProvidersResult } from "../../../../hooks/settings/useProviders.js";
import { MaskedKeyInput } from "./shared.js";

interface ProvidersSectionProps {
  providers: UseProvidersResult;
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
  const isOAuth = current?.id === "claude_oauth";
  const isCustom = current?.id === "custom";

  return (
    <box flexDirection="column">
      {s.items.map((provider, i) => {
        const selected = i === s.selectedIndex;
        const providerIsCustom = provider.id === "custom";
        const providerIsOAuth = provider.id === "claude_oauth";
        const isEditing = selected && s.editing && !providerIsCustom && !providerIsOAuth;

        return (
          <box key={provider.id} flexDirection="column">
            <box flexDirection="row">
              <text>
                <span fg={selected ? accent : colors.text.disabled}>{selected ? "\u25B8 " : "  "}</span>
                <span fg={selected ? colors.text.primary : colors.text.secondary}>{provider.name.padEnd(28)}</span>
              </text>
              {providerIsCustom ? (
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
                      <span fg={colors.text.disabled}>{provider.key_hint ?? (providerIsOAuth ? "oauth" : "")}</span>
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

      {s.oauthConnecting && (
        <box marginTop={1}>
          <text><span fg={colors.text.muted}>  Waiting for browser login...</span></text>
        </box>
      )}

      {!s.editing && !s.confirmDisconnect && !s.saving && !s.oauthConnecting && (
        <box marginTop={1} marginLeft={2}>
          {isCustom ? (
            <text><span fg={colors.text.disabled}>use /connect to manage custom models</span></text>
          ) : isOAuth && current.connected ? (
            <Hints items={[["d", "disconnect"]]} />
          ) : isOAuth && !current.connected ? (
            <Hints items={[["enter", "connect via browser"]]} />
          ) : current && current.connected && !current.from_env ? (
            <Hints items={[["enter", "edit"], ["d", "disconnect"]]} />
          ) : current?.from_env ? (
            <text><span fg={colors.text.disabled}>set via environment variable</span></text>
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
