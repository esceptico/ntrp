import { Box, Text } from "ink";
import { colors, truncateText, SelectionIndicator } from "../../ui/index.js";
import type { ServerConfig, GmailAccount } from "../../../api/client.js";
import { CONNECTION_LABELS, type ConnectionItem } from "./config.js";

interface ConnectionsSectionProps {
  serverConfig: ServerConfig | null;
  googleAccounts: GmailAccount[];
  selectedItem: ConnectionItem;
  selectedGoogleIndex: number;
  accent: string;
  width: number;
}

export function ConnectionsSection({
  serverConfig,
  googleAccounts,
  selectedItem,
  selectedGoogleIndex,
  accent,
  width,
}: ConnectionsSectionProps) {
  const labelWidth = 14;
  const valueWidth = Math.max(0, width - labelWidth - 6);

  return (
    <Box flexDirection="column">
      {/* Vault */}
      <ConnectionRow
        item="vault"
        selected={selectedItem === "vault"}
        accent={accent}
      >
        <Text color={colors.text.primary}>
          {truncateText(serverConfig?.vault_path || "—", valueWidth)}
        </Text>
      </ConnectionRow>

      {/* Google */}
      <ConnectionRow
        item="google"
        selected={selectedItem === "google"}
        accent={accent}
      >
        {googleAccounts.length === 0 ? (
          <Text color={colors.text.muted}>No accounts</Text>
        ) : (
          <Text color={colors.text.primary}>
            {googleAccounts.length} account{googleAccounts.length !== 1 ? "s" : ""}
          </Text>
        )}
      </ConnectionRow>

      {/* Show Google accounts when selected */}
      {selectedItem === "google" && googleAccounts.length > 0 && (
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

      {/* Browser */}
      <ConnectionRow
        item="browser"
        selected={selectedItem === "browser"}
        accent={accent}
      >
        {serverConfig?.has_browser ? (
          <Text color={colors.text.primary}>{serverConfig.browser}</Text>
        ) : (
          <Text color={colors.text.muted}>Not configured</Text>
        )}
      </ConnectionRow>

      {/* Help text */}
      <Box marginTop={1}>
        <Text color={colors.text.disabled}>
          {selectedItem === "google"
            ? "a: add account · d: remove"
            : "Google: manage accounts"}
        </Text>
      </Box>
    </Box>
  );
}

interface ConnectionRowProps {
  item: ConnectionItem;
  selected: boolean;
  accent: string;
  children: React.ReactNode;
}

function ConnectionRow({ item, selected, accent, children }: ConnectionRowProps) {
  const label = CONNECTION_LABELS[item].padEnd(14);
  return (
    <Text>
      <SelectionIndicator selected={selected} accent={accent} />
      <Text color={selected ? colors.text.primary : colors.text.secondary}>{label}</Text>
      {children}
    </Text>
  );
}
