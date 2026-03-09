import { colors, Hints } from "../../../ui/index.js";
import type { ProviderInfo } from "../../../../api/client.js";
import type { UseProvidersResult } from "../../../../hooks/settings/useProviders.js";
import { CredentialSection } from "./CredentialSection.js";

interface ProvidersSectionProps {
  providers: UseProvidersResult;
  accent: string;
}

function renderStatus(provider: ProviderInfo, _selected: boolean) {
  if (provider.id === "custom") {
    return (
      <text>
        <span fg={provider.connected ? colors.status.success : colors.text.disabled}>
          {provider.model_count ? `${provider.model_count} model${provider.model_count !== 1 ? "s" : ""}` : "none"}
        </span>
      </text>
    );
  }
  if (provider.connected) {
    return (
      <text>
        <span fg={colors.status.success}>{"\u2713 "}</span>
        <span fg={colors.text.disabled}>{provider.key_hint ?? (provider.id === "claude_oauth" ? "oauth" : "")}</span>
        {provider.from_env && <span fg={colors.text.muted}>{" (env)"}</span>}
      </text>
    );
  }
  return <text><span fg={colors.text.disabled}>not connected</span></text>;
}

function renderHints(item: ProviderInfo) {
  if (item?.id === "custom") {
    return <text><span fg={colors.text.disabled}>use /connect to manage custom models</span></text>;
  }
  if (item?.id === "claude_oauth") {
    return item.connected
      ? <Hints items={[["d", "disconnect"]]} />
      : <Hints items={[["enter", "connect via browser"]]} />;
  }
  if (item?.connected && !item.from_env) {
    return null;
  }
  if (item?.from_env) {
    return <text><span fg={colors.text.disabled}>set via environment variable</span></text>;
  }
  return null;
}

export function ProvidersSection({ providers, accent }: ProvidersSectionProps) {
  return (
    <box flexDirection="column">
      <CredentialSection
        state={providers}
        accent={accent}
        labelWidth={28}
        renderStatus={renderStatus}
        renderHints={renderHints}
        isEditable={(p) => p.id !== "custom" && p.id !== "claude_oauth"}
      />
      {providers.oauthConnecting && (
        <box marginTop={1}>
          <text><span fg={colors.text.muted}>  Waiting for browser login...</span></text>
        </box>
      )}
    </box>
  );
}
