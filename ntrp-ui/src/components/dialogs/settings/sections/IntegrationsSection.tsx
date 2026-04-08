import { colors, truncateText } from "../../../ui/index.js";
import { TextInputField } from "../../../ui/input/TextInputField.js";
import { SelectionIndicator } from "../../../ui/index.js";
import type { ServerConfig, GoogleAccount } from "../../../../api/client.js";
import { INTEGRATION_LABELS, type IntegrationItem } from "../config.js";
import { Header, Row as SettingsRow } from "../SettingsRows.js";
import type { UseConnectionsResult } from "../../../../hooks/settings/useConnections.js";
import type { UseServicesResult } from "../../../../hooks/settings/useServices.js";
import { CredentialSection } from "./CredentialSection.js";

interface IntegrationsSectionProps {
  connections: UseConnectionsResult;
  services: UseServicesResult;
  activeList: "connections" | "services";
  serverConfig: ServerConfig | null;
  accent: string;
  width: number;
}

export function IntegrationsSection({ connections: c, services, activeList, serverConfig, accent, width }: IntegrationsSectionProps) {
  const inactiveAccent = colors.text.disabled;
  const valueWidth = Math.max(0, width - 20);
  const integrations = serverConfig?.integrations;
  const isGoogleItem = c.sourceItem === "google";
  const googleEnabled = isGoogleItem && integrations?.google?.enabled;

  const connectionsAccent = activeList === "connections" ? accent : inactiveAccent;
  const servicesAccent = activeList === "services" ? accent : inactiveAccent;

  return (
    <box flexDirection="column">
      <Header first>Connections</Header>
      <Row item="vault" selected={c.sourceItem === "vault"} accent={connectionsAccent}>
        {c.vault.editingVault ? (
          <box flexDirection="row">
            <text><span fg={colors.text.muted}>[</span></text>
            <TextInputField
              value={c.vault.vaultPath}
              cursorPos={c.vault.vaultCursorPos}
              placeholder="Enter vault path..."
              showCursor={true}
              textColor={colors.text.primary}
            />
            <text><span fg={colors.text.muted}>]</span></text>
          </box>
        ) : c.vault.updatingVault ? (
          <text><span fg={colors.status.warning}>Updating...</span></text>
        ) : (
          <text>
            <span fg={serverConfig?.vault_path ? colors.text.primary : colors.text.muted}>
              {truncateText(serverConfig?.vault_path || "Not configured", valueWidth)}
            </span>
          </text>
        )}
      </Row>
      {c.vault.vaultError && (
        <box marginLeft={4}>
          <text><span fg={colors.status.error}>{c.vault.vaultError}</span></text>
        </box>
      )}

      <GoogleRow item="google" selectedItem={c.sourceItem} integrations={integrations} accounts={c.googleAccounts} accent={connectionsAccent} />

      {isGoogleItem && googleEnabled && c.googleAccounts.length > 0 && (
        <AccountList accounts={c.googleAccounts} selectedIndex={c.selectedGoogleIndex} accent={connectionsAccent} valueWidth={valueWidth} />
      )}

      <Row item="web" selected={c.sourceItem === "web"} accent={connectionsAccent}>
        <text>
          {c.sourceItem === "web" && <span fg={colors.text.muted}>◂ </span>}
          <span fg={integrations?.web?.connected ? colors.text.primary : colors.text.muted}>
            {formatWebSearchStatus(serverConfig)}
          </span>
          {c.sourceItem === "web" && <span fg={colors.text.muted}> ▸</span>}
        </text>
      </Row>

      <Header>Credentials</Header>
      <CredentialSection state={services} accent={servicesAccent} />

    </box>
  );
}

function formatWebSearchStatus(serverConfig: ServerConfig | null): string {
  if (!serverConfig) return "Loading...";
  const mode = serverConfig.web_search;
  const provider = serverConfig.web_search_provider;
  if (mode === "none") return "Disabled";
  if (mode === "auto") {
    if (provider === "none") return "Auto (disabled)";
    return `Auto (${provider.toUpperCase()})`;
  }
  return `${mode.toUpperCase()}${provider !== "none" ? ` (${provider.toUpperCase()})` : ""}`;
}

function GoogleRow({ item, selectedItem, integrations, accounts, accent }: {
  item: IntegrationItem;
  selectedItem: IntegrationItem;
  integrations?: Record<string, { enabled?: boolean; connected?: boolean; error?: string }>;
  accounts: GoogleAccount[];
  accent: string;
}) {
  const entry = integrations?.[item];
  const hasTokens = accounts.length > 0;
  const selected = selectedItem === item;
  const hasError = !!entry?.error;

  return (
    <Row item={item} selected={selected} accent={accent}>
      <Toggle enabled={entry?.enabled} connected={hasTokens} error={hasError} accent={accent} />
      {hasError ? (
        <text><span fg={colors.status.error}>Auth expired — remove & re-add account</span></text>
      ) : entry?.enabled ? (
        hasTokens ? (
          <text><span fg={colors.text.primary}>{accounts.length} account{accounts.length !== 1 ? "s" : ""}</span></text>
        ) : (
          <text><span fg={colors.status.warning}>No accounts</span></text>
        )
      ) : (
        <text><span fg={colors.text.muted}>Disabled</span></text>
      )}
    </Row>
  );
}

function AccountList({ accounts, selectedIndex, accent, valueWidth }: {
  accounts: GoogleAccount[];
  selectedIndex: number;
  accent: string;
  valueWidth: number;
}) {
  return (
    <box flexDirection="column" marginLeft={4}>
      {accounts.map((account, i) => {
        const selected = i === selectedIndex;
        const email = account.email || account.token_file;
        return (
          <text key={account.token_file}>
            <SelectionIndicator selected={selected} accent={accent} />
            <span fg={account.error ? colors.status.error : (selected ? accent : colors.text.secondary)}>
              {truncateText(email, valueWidth - 4)}
            </span>
            {account.error && <span fg={colors.status.error}> !</span>}
          </text>
        );
      })}
    </box>
  );
}

function Row({ item, selected, accent, children }: {
  item: IntegrationItem;
  selected: boolean;
  accent: string;
  children: React.ReactNode;
}) {
  return (
    <SettingsRow selected={selected} accent={accent} label={INTEGRATION_LABELS[item]} labelWidth={14}>
      {children}
    </SettingsRow>
  );
}

function Toggle({ enabled, connected, error, accent }: { enabled?: boolean; connected?: boolean; error?: boolean; accent: string }) {
  if (!enabled) {
    return <text><span fg={colors.text.muted}>○ </span></text>;
  }
  const color = error ? colors.status.error : connected !== false ? accent : colors.status.warning;
  return <text><span fg={color}>● </span></text>;
}
