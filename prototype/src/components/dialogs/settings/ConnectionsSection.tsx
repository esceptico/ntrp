import { colors, truncateText, SelectionIndicator, Hints } from "../../ui/index.js";
import { TextInputField } from "../../ui/input/TextInputField.js";
import { CHECKBOX_CHECKED, CHECKBOX_UNCHECKED } from "../../../lib/constants.js";
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
  const labelWidth = 14;
  const valueWidth = Math.max(0, width - labelWidth - 6);
  const sources = serverConfig?.sources;
  const isGoogleSource = GOOGLE_SOURCES.includes(selectedItem);
  const sourceEnabled = isGoogleSource && sources?.[selectedItem]?.enabled;

  return (
    <box flexDirection="column">
      {/* Vault / Notes */}
      <SourceRow item="vault" selected={selectedItem === "vault"} accent={accent}>
        {editingVault ? (
          <box flexDirection="row">
            <text>
              <span fg={colors.text.muted}>[</span>
            </text>
            <TextInputField
              value={vaultPath}
              cursorPos={vaultCursorPos}
              placeholder="Enter vault path..."
              showCursor={true}
              textColor={colors.text.primary}
            />
            <text>
              <span fg={colors.text.muted}>]</span>
            </text>
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
      </SourceRow>
      {vaultError && (
        <box marginLeft={4}>
          <text><span fg={colors.status.error}>{vaultError}</span></text>
        </box>
      )}

      {/* Gmail */}
      <GoogleSourceRow
        item="gmail"
        selectedItem={selectedItem}
        sources={sources}
        googleAccounts={googleAccounts}
        accent={accent}
      />

      {selectedItem === "gmail" && sourceEnabled && googleAccounts.length > 0 && (
        <GoogleAccountList
          accounts={googleAccounts}
          selectedIndex={selectedGoogleIndex}
          accent={accent}
          valueWidth={valueWidth}
        />
      )}

      {/* Calendar */}
      <GoogleSourceRow
        item="calendar"
        selectedItem={selectedItem}
        sources={sources}
        googleAccounts={googleAccounts}
        accent={accent}
      />

      {selectedItem === "calendar" && sourceEnabled && googleAccounts.length > 0 && (
        <GoogleAccountList
          accounts={googleAccounts}
          selectedIndex={selectedGoogleIndex}
          accent={accent}
          valueWidth={valueWidth}
        />
      )}

      {/* Browser */}
      <SourceRow item="browser" selected={selectedItem === "browser"} accent={accent}>
        {updatingBrowser ? (
          <text><span fg={colors.status.warning}>Updating...</span></text>
        ) : serverConfig?.has_browser ? (
          <text><span fg={colors.text.primary}>{serverConfig.browser}</span></text>
        ) : (
          <text><span fg={colors.text.muted}>Not configured</span></text>
        )}
      </SourceRow>
      {browserError && (
        <box marginLeft={4}>
          <text><span fg={colors.status.error}>{browserError}</span></text>
        </box>
      )}

      {/* Memory */}
      <SourceRow item="memory" selected={selectedItem === "memory"} accent={accent}>
        <ToggleIndicator source={sources?.memory} accent={accent} />
        <text>
          <span fg={sources?.memory?.enabled ? colors.text.primary : colors.text.muted}>
            {sources?.memory?.enabled ? "Active" : "Disabled"}
          </span>
        </text>
      </SourceRow>

      {/* Web Search */}
      <SourceRow item="web" selected={selectedItem === "web"} accent={accent}>
        <text>
          <span fg={sources?.web?.connected ? colors.text.primary : colors.text.muted}>
            {sources?.web?.connected ? "Connected" : "Not configured"}
          </span>
        </text>
      </SourceRow>

      {/* Help text */}
      <box marginTop={1}>
        {getHints(selectedItem, editingVault, sourceEnabled)}
      </box>
    </box>
  );
}

function getHints(item: ConnectionItem, editingVault: boolean, sourceEnabled?: boolean): React.ReactNode {
  switch (item) {
    case "vault":
      return editingVault
        ? <Hints items={[["enter", "save"], ["esc", "cancel"]]} />
        : <Hints items={[["enter", "edit path"]]} />;
    case "gmail":
    case "calendar":
      return sourceEnabled
        ? <Hints items={[["enter", "toggle"], ["a", "add account"], ["d", "remove"]]} />
        : <Hints items={[["enter", "toggle"]]} />;
    case "memory":
      return <Hints items={[["enter", "toggle"]]} />;
    case "browser":
      return <Hints items={[["enter", "change browser"]]} />;
    case "web":
      return null;
  }
}

interface GoogleSourceRowProps {
  item: ConnectionItem;
  selectedItem: ConnectionItem;
  sources?: Record<string, { enabled?: boolean; connected?: boolean }>;
  googleAccounts: GoogleAccount[];
  accent: string;
}

function GoogleSourceRow({ item, selectedItem, sources, googleAccounts, accent }: GoogleSourceRowProps) {
  const source = sources?.[item];
  const hasTokens = googleAccounts.length > 0;
  return (
    <SourceRow item={item} selected={selectedItem === item} accent={accent}>
      <ToggleIndicator source={source ? { ...source, connected: hasTokens } : source} accent={accent} />
      {source?.enabled ? (
        hasTokens ? (
          <text>
            <span fg={colors.text.primary}>
              {googleAccounts.length} account{googleAccounts.length !== 1 ? "s" : ""}
            </span>
          </text>
        ) : (
          <text><span fg={colors.status.warning}>No tokens</span></text>
        )
      ) : (
        <text><span fg={colors.text.muted}>Disabled</span></text>
      )}
    </SourceRow>
  );
}

interface GoogleAccountListProps {
  accounts: GoogleAccount[];
  selectedIndex: number;
  accent: string;
  valueWidth: number;
}

function GoogleAccountList({ accounts, selectedIndex, accent, valueWidth }: GoogleAccountListProps) {
  return (
    <box flexDirection="column" marginLeft={4}>
      {accounts.map((account, i) => {
        const isSelected = i === selectedIndex;
        const email = account.email || account.token_file;
        return (
          <text key={account.token_file}>
            <SelectionIndicator selected={isSelected} accent={accent} />
            <span fg={account.error ? colors.status.error : (isSelected ? accent : colors.text.secondary)}>
              {truncateText(email, valueWidth - 4)}
            </span>
            {account.error && <span fg={colors.status.error}> !</span>}
          </text>
        );
      })}
    </box>
  );
}

interface SourceRowProps {
  item: ConnectionItem;
  selected: boolean;
  accent: string;
  children: React.ReactNode;
}

function SourceRow({ item, selected, accent, children }: SourceRowProps) {
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

interface ToggleIndicatorProps {
  source?: { enabled?: boolean; connected?: boolean };
  accent: string;
}

function ToggleIndicator({ source, accent }: ToggleIndicatorProps) {
  const enabled = source?.enabled ?? false;
  const connected = source?.connected ?? false;

  if (!enabled) {
    return <text><span fg={colors.text.muted}>{CHECKBOX_UNCHECKED}</span></text>;
  }
  const indicatorColor = connected ? accent : colors.status.warning;
  return <text><span fg={indicatorColor}>{CHECKBOX_CHECKED}</span></text>;
}
