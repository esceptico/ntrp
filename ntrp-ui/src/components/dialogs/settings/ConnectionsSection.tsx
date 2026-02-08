import { Box, Text } from "ink";
import { colors, truncateText, SelectionIndicator } from "../../ui/index.js";
import { TextInputField } from "../../ui/input/TextInputField.js";
import { CHECKBOX_CHECKED, CHECKBOX_UNCHECKED } from "../../../lib/constants.js";
import type { ServerConfig, GoogleAccount } from "../../../api/client.js";
import { CONNECTION_LABELS, type ConnectionItem } from "./config.js";

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
      <SourceRow item="gmail" selected={selectedItem === "gmail"} accent={accent}>
        <ToggleIndicator source={sources?.gmail} accent={accent} />
        {sources?.gmail?.enabled ? (
          googleAccounts.length === 0 ? (
            <Text color={colors.text.muted}>No accounts</Text>
          ) : (
            <Text color={colors.text.primary}>
              {googleAccounts.length} account{googleAccounts.length !== 1 ? "s" : ""}
            </Text>
          )
        ) : (
          <Text color={colors.text.muted}>Disabled</Text>
        )}
      </SourceRow>

      {/* Gmail accounts sub-list */}
      {selectedItem === "gmail" && sources?.gmail?.enabled && googleAccounts.length > 0 && (
        <Box flexDirection="column" marginLeft={4}>
          {googleAccounts.map((account, i) => {
            const isSelected = i === selectedGoogleIndex;
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
      )}

      {/* Calendar — shares Google OAuth tokens with Gmail */}
      <SourceRow item="calendar" selected={selectedItem === "calendar"} accent={accent}>
        <ToggleIndicator source={sources?.calendar ? { ...sources.calendar, connected: googleAccounts.length > 0 } : sources?.calendar} accent={accent} />
        {sources?.calendar?.enabled ? (
          googleAccounts.length > 0 ? (
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
          {getHelpText(selectedItem, editingVault, sources?.gmail?.enabled)}
        </Text>
      </Box>
    </Box>
  );
}

function getHelpText(item: ConnectionItem, editingVault: boolean, gmailEnabled?: boolean): string {
  switch (item) {
    case "vault":
      return editingVault ? "Enter: save · Esc: cancel" : "Enter: edit path";
    case "gmail":
      return gmailEnabled ? "Enter: toggle · a: add account · d: remove" : "Enter: toggle";
    case "calendar":
    case "memory":
      return "Enter: toggle";
    case "browser":
      return "Enter: change browser";
    case "web":
      return "";
  }
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
