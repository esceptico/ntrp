import React from "react";
import { Box, Text } from "ink";
import type { GmailAccount } from "../../../api/client.js";
import { colors, truncateText } from "../../ui/index.js";
import { BULLET } from "../../../lib/constants.js";

interface GmailSectionProps {
  accounts: GmailAccount[];
  selectedIndex: number;
  width: number;
}

export function GmailSection({ accounts, selectedIndex, width }: GmailSectionProps) {
  const emailMaxWidth = Math.max(0, width - 10);

  if (accounts.length === 0) {
    return (
      <Box flexDirection="column" marginY={1} width={width} overflow="hidden">
        <Text color={colors.text.secondary}>No accounts connected. Press 'a' to add.</Text>
      </Box>
    );
  }

  return (
    <Box flexDirection="column" marginY={1} width={width} overflow="hidden">
      {accounts.map((account, i) => {
        const isSelected = i === selectedIndex;
        const hasError = !!account.error;
        const email = truncateText(account.email || account.token_file, emailMaxWidth);
        const suffix = account.has_send_scope === false && !hasError ? " (read-only)" : "";

        return (
          <Text key={account.token_file}>
            <Text color={isSelected ? colors.selection.indicator : colors.text.disabled}>
              {isSelected ? "> " : "  "}
            </Text>
            <Text color={hasError ? colors.status.error : (isSelected ? colors.selection.active : colors.status.success)}>
              {hasError ? "✗" : BULLET}
            </Text>
            <Text color={isSelected ? colors.list.itemTextSelected : colors.list.itemText} bold={isSelected}>
              {" "}{email}
            </Text>
            {suffix && <Text color={colors.text.secondary}>{suffix}</Text>}
          </Text>
        );
      })}

      <Box marginTop={1}>
        <Text color={colors.text.muted}>
          {selectedIndex + 1} of {accounts.length}
        </Text>
      </Box>
    </Box>
  );
}
