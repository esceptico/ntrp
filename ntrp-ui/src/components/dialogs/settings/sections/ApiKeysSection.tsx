import { colors } from "../../../ui/index.js";
import type { ProviderInfo } from "../../../../api/client.js";
import type { UseProvidersResult } from "../../../../hooks/settings/useProviders.js";
import type { UseServicesResult } from "../../../../hooks/settings/useServices.js";
import { CredentialSection } from "./CredentialSection.js";
import { Header } from "../SettingsRows.js";

interface ApiKeysSectionProps {
  providers: UseProvidersResult;
  services: UseServicesResult;
  activeList: "providers" | "services";
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
  return <text><span fg={colors.text.disabled}>not connected</span></text>;
}

export function ApiKeysSection({ providers, services, activeList, accent }: ApiKeysSectionProps) {
  const inactiveAccent = colors.text.disabled;

  return (
    <box flexDirection="column">
      <Header first>Providers</Header>
      <CredentialSection
        state={providers}
        accent={activeList === "providers" ? accent : inactiveAccent}
        labelWidth={28}
        renderStatus={renderProviderStatus}
        isEditable={(p) => p.id !== "custom"}
      />

      <Header>Services</Header>
      <CredentialSection
        state={services}
        accent={activeList === "services" ? accent : inactiveAccent}
      />
    </box>
  );
}
