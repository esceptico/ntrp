import { colors } from "../../../ui/index.js";
import type { ProviderInfo } from "../../../../api/client.js";
import type { UseProvidersResult } from "../../../../hooks/settings/useProviders.js";
import { CredentialSection } from "./CredentialSection.js";

interface ApiKeysSectionProps {
  providers: UseProvidersResult;
  accent: string;
}

function renderProviderStatus(provider: ProviderInfo, _selected: boolean) {
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
        <span fg={colors.text.disabled}>{provider.key_hint ?? ""}</span>
        {provider.from_env && <span fg={colors.text.muted}>{" (env)"}</span>}
      </text>
    );
  }
  if (provider.auth_type === "oauth") {
    return <text><span fg={colors.text.disabled}>browser sign-in</span></text>;
  }
  return <text><span fg={colors.text.disabled}>not connected</span></text>;
}

export function ApiKeysSection({ providers, accent }: ApiKeysSectionProps) {
  return (
    <box flexDirection="column">
      <CredentialSection
        state={providers}
        accent={accent}
        labelWidth={28}
        renderStatus={renderProviderStatus}
        isEditable={(p) => p.id !== "custom" && p.auth_type !== "oauth"}
      />
    </box>
  );
}
