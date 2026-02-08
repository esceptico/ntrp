import { Box, Text } from "ink";
import { colors, truncateText, SelectionIndicator } from "../../ui/index.js";
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
    <Box flexDirection="column">
      {/* Vault / Notes */}
      <SourceRow item="vault" selected={selectedItem === "vault"} accent={accent}>
        {editingVault ? (
          <Box>
            <Text color={colors.text.muted}>[</Text>
            <TextInputField
              value={vaultPath}
              cursorPos={vaultCursorPos}
              placeholder="Enter vault path..."
              showCursor={true}
              textColor={colors.text.primary}
            />
            <Text color={colors.text.muted}>]</Text>
          </Box>
        ) : updatingVault ? (
          <Text color={colors.status.warning}>Updating...</Text>
        ) : (
          <Text color={serverConfig?.vault_path ? colors.text.primary : colors.text.muted}>
            {truncateText(serverConfig?.vault_path || "Not configured", valueWidth)}
          </Text>
        )}
      </SourceRow>
      {vaultError && (
        <Box marginLeft={4}>
          <Text color={colors.status.error}>{vaultError}</Text>
        </Box>
      )}

      {/* Gmail */}
      <GoogleSourceRow
        item="gmail"
        selectedItem={selectedItem}
        sources={sources}
        googleAccounts={googleAccounts}
        accent={accent}
      />

      {/* Gmail accounts sub-list */}
      {selectedItem === "gmail" && sourceEnabled && googleAccounts.length > 0 && (
        <GoogleAccountList
          accounts={googleAccounts}
          selectedIndex={selectedGoogleIndex}
          accent={accent}
          valueWidth={valueWidth}
        />
      )}

      {/* Calendar — shares Google OAuth tokens with Gmail */}
      <GoogleSourceRow
        item="calendar"
        selectedItem={selectedItem}
        sources={sources}
        googleAccounts={googleAccounts}
        accent={accent}
      />

      {/* Calendar accounts sub-list */}
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
          <Text color={colors.status.warning}>Updating...</Text>
        ) : serverConfig?.has_browser ? (
          <Text color={colors.text.primary}>{serverConfig.browser}</Text>
        ) : (
          <Text color={colors.text.muted}>Not configured</Text>
        )}
      </SourceRow>
      {browserError && (
        <Box marginLeft={4}>
          <Text color={colors.status.error}>{browserError}</Text>
        </Box>
      )}

      {/* Memory */}
      <SourceRow item="memory" selected={selectedItem === "memory"} accent={accent}>
        <ToggleIndicator source={sources?.memory} accent={accent} />
        <Text color={sources?.memory?.enabled ? colors.text.primary : colors.text.muted}>
          {sources?.memory?.enabled ? "Active" : "Disabled"}
        </Text>
      </SourceRow>

      {/* Web Search */}
      <SourceRow item="web" selected={selectedItem === "web"} accent={accent}>
        <Text color={sources?.web?.connected ? colors.text.primary : colors.text.muted}>
          {sources?.web?.connected ? "Connected" : "Not configured"}
        </Text>
      </SourceRow>

      {/* Help text */}
      <Box marginTop={1}>
        <Text color={colors.text.disabled}>
          {getHelpText(selectedItem, editingVault, sourceEnabled)}
        </Text>
      </Box>
    </Box>
  );
}

function getHelpText(item: ConnectionItem, editingVault: boolean, sourceEnabled?: boolean): string {
  switch (item) {
    case "vault":
      return editingVault ? "Enter: save · Esc: cancel" : "Enter: edit path";
    case "gmail":
    case "calendar":
      return sourceEnabled ? "Enter: toggle · a: add account · d: remove" : "Enter: toggle";
    case "memory":
      return "Enter: toggle";
    case "browser":
      return "Enter: change browser";
    case "web":
      return "";
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
          <Text color={colors.text.primary}>
            {googleAccounts.length} account{googleAccounts.length !== 1 ? "s" : ""}
          </Text>
        ) : (
          <Text color={colors.status.warning}>No tokens</Text>
        )
      ) : (
        <Text color={colors.text.muted}>Disabled</Text>
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
    <Box flexDirection="column" marginLeft={4}>
      {accounts.map((account, i) => {
        const isSelected = i === selectedIndex;
        const email = account.email || account.token_file;
        return (
          <Text key={account.token_file}>
            <SelectionIndicator selected={isSelected} accent={accent} />
            <Text color={account.error ? colors.status.error : (isSelected ? accent : colors.text.secondary)}>
              {truncateText(email, valueWidth - 4)}
            </Text>
            {account.error && <Text color={colors.status.error}> !</Text>}
          </Text>
        );
      })}
    </Box>
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
    <Box>
      <SelectionIndicator selected={selected} accent={accent} />
      <Text color={selected ? colors.text.primary : colors.text.secondary}>{label}</Text>
      {children}
    </Box>
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
    return <Text color={colors.text.muted}>{CHECKBOX_UNCHECKED}</Text>;
  }
  const indicatorColor = connected ? accent : colors.status.warning;
  return <Text color={indicatorColor}>{CHECKBOX_CHECKED}</Text>;
}
