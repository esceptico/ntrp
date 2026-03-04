import { colors, truncateText, SelectionIndicator, Hints } from "../../ui/index.js";
import { TextInputField } from "../../ui/input/TextInputField.js";
import type { ServerConfig, GoogleAccount } from "../../../api/client.js";
import { CONNECTION_LABELS, type ConnectionItem } from "./config.js";

const GOOGLE_SOURCES: ConnectionItem[] = ["gmail", "calendar"];

interface ConnectionsSectionProps {
  serverConfig: ServerConfig | null;
  googleAccounts: GoogleAccount[];
  selectedItem: ConnectionItem;
  selectedGoogleIndex: number;
  accent: string;
  width: number;
  editingVault: boolean;
  vaultPath: string;
  vaultCursorPos: number;
  updatingVault: boolean;
  vaultError: string | null;
  updatingBrowser: boolean;
  browserError: string | null;
}

export function ConnectionsSection({
  serverConfig,
  googleAccounts,
  selectedItem,
  selectedGoogleIndex,
  accent,
  width,
  editingVault,
  vaultPath,
  vaultCursorPos,
  updatingVault,
  vaultError,
  updatingBrowser,
  browserError,
}: ConnectionsSectionProps) {
  const valueWidth = Math.max(0, width - 20);
  const sources = serverConfig?.sources;
  const isGoogleSource = GOOGLE_SOURCES.includes(selectedItem);
  const sourceEnabled = isGoogleSource && sources?.[selectedItem]?.enabled;

  return (
    <box flexDirection="column">
      {/* Vault / Notes */}
      <Row item="vault" selected={selectedItem === "vault"} accent={accent}>
        {editingVault ? (
          <box flexDirection="row">
            <text><span fg={colors.text.muted}>[</span></text>
            <TextInputField
              value={vaultPath}
              cursorPos={vaultCursorPos}
              placeholder="Enter vault path..."
              showCursor={true}
              textColor={colors.text.primary}
            />
            <text><span fg={colors.text.muted}>]</span></text>
          </box>
        ) : updatingVault ? (
          <text><span fg={colors.status.warning}>Updating...</span></text>
        ) : (
          <text>
            <span fg={serverConfig?.vault_path ? colors.text.primary : colors.text.muted}>
              {truncateText(serverConfig?.vault_path || "Not configured", valueWidth)}
            </span>
          </text>
        )}
      </Row>
      {vaultError && (
        <box marginLeft={4}>
          <text><span fg={colors.status.error}>{vaultError}</span></text>
        </box>
      )}

      {/* Gmail */}
      <GoogleRow item="gmail" selectedItem={selectedItem} sources={sources} accounts={googleAccounts} accent={accent} />

      {selectedItem === "gmail" && sourceEnabled && googleAccounts.length > 0 && (
        <AccountList accounts={googleAccounts} selectedIndex={selectedGoogleIndex} accent={accent} valueWidth={valueWidth} />
      )}

      {/* Calendar */}
      <GoogleRow item="calendar" selectedItem={selectedItem} sources={sources} accounts={googleAccounts} accent={accent} />

      {selectedItem === "calendar" && sourceEnabled && googleAccounts.length > 0 && (
        <AccountList accounts={googleAccounts} selectedIndex={selectedGoogleIndex} accent={accent} valueWidth={valueWidth} />
      )}

      {/* Browser */}
      <Row item="browser" selected={selectedItem === "browser"} accent={accent}>
        {updatingBrowser ? (
          <text><span fg={colors.status.warning}>Updating...</span></text>
        ) : serverConfig?.has_browser ? (
          <text><span fg={colors.text.primary}>{serverConfig.browser}</span></text>
        ) : (
          <text><span fg={colors.text.muted}>Not configured</span></text>
        )}
      </Row>
      {browserError && (
        <box marginLeft={4}>
          <text><span fg={colors.status.error}>{browserError}</span></text>
        </box>
      )}

      {/* Memory */}
      <Row item="memory" selected={selectedItem === "memory"} accent={accent}>
        <Toggle enabled={sources?.memory?.enabled} accent={accent} />
        <text>
          <span fg={sources?.memory?.enabled ? colors.text.primary : colors.text.muted}>
            {sources?.memory?.enabled ? "Active" : "Disabled"}
          </span>
        </text>
      </Row>

      {/* Web Search */}
      <Row item="web" selected={selectedItem === "web"} accent={accent}>
        <text>
          <span fg={sources?.web?.connected ? colors.text.primary : colors.text.muted}>
            {sources?.web?.connected ? "Connected" : "Not configured"}
          </span>
        </text>
      </Row>

      {/* Hints — always visible */}
      <box marginTop={1}>
        <HintRow item={selectedItem} editingVault={editingVault} sourceEnabled={sourceEnabled} />
      </box>
    </box>
  );
}

function HintRow({ item, editingVault, sourceEnabled }: { item: ConnectionItem; editingVault: boolean; sourceEnabled?: boolean }) {
  switch (item) {
    case "vault":
      return editingVault
        ? <Hints items={[["enter", "save"], ["esc", "cancel"]]} />
        : <Hints items={[["enter", "edit path"]]} />;
    case "gmail":
    case "calendar":
      if (sourceEnabled) {
        return <Hints items={[["enter", "toggle"], ["a", "add account"], ["d", "remove account"]]} />;
      }
      return <Hints items={[["enter", "enable"]]} />;
    case "memory":
      return <Hints items={[["enter", "toggle"]]} />;
    case "browser":
      return <Hints items={[["enter", "change browser"]]} />;
    case "web":
      return <Hints items={[]} />;
  }
}

function GoogleRow({ item, selectedItem, sources, accounts, accent }: {
  item: ConnectionItem;
  selectedItem: ConnectionItem;
  sources?: Record<string, { enabled?: boolean; connected?: boolean; error?: string }>;
  accounts: GoogleAccount[];
  accent: string;
}) {
  const source = sources?.[item];
  const hasTokens = accounts.length > 0;
  const selected = selectedItem === item;
  const hasError = !!source?.error;

  return (
    <Row item={item} selected={selected} accent={accent}>
      <Toggle enabled={source?.enabled} connected={hasTokens} error={hasError} accent={accent} />
      {hasError ? (
        <text><span fg={colors.status.error}>Auth expired — remove & re-add account</span></text>
      ) : source?.enabled ? (
        hasTokens ? (
          <text>
            <span fg={colors.text.primary}>
              {accounts.length} account{accounts.length !== 1 ? "s" : ""}
            </span>
          </text>
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
  item: ConnectionItem;
  selected: boolean;
  accent: string;
  children: React.ReactNode;
}) {
  const label = CONNECTION_LABELS[item].padEnd(14);
  return (
    <box flexDirection="row">
      <text>
        <SelectionIndicator selected={selected} accent={accent} />
        <span fg={selected ? colors.text.primary : colors.text.secondary}>{label}</span>
      </text>
      {children}
    </box>
  );
}

function Toggle({ enabled, connected, error, accent }: { enabled?: boolean; connected?: boolean; error?: boolean; accent: string }) {
  if (!enabled) {
    return <text><span fg={colors.text.muted}>○ </span></text>;
  }
  const color = error ? colors.status.error : connected !== false ? accent : colors.status.warning;
  return <text><span fg={color}>● </span></text>;
}
