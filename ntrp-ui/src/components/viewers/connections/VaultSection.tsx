import React from "react";
import { Box, Text } from "ink";
import type { ServerConfig } from "../../../api/client.js";
import { colors, truncateText } from "../../ui/index.js";
import { BULLET } from "../../../lib/constants.js";

interface VaultSectionProps {
  serverConfig: ServerConfig;
  width: number;
}

export function VaultSection({ serverConfig, width }: VaultSectionProps) {
  return (
    <Box flexDirection="column" marginY={1} width={width} overflow="hidden">
      <Text>
        <Text color={colors.status.success}>{BULLET}</Text>
        <Text> {truncateText(String(serverConfig.vault_path), width - 4)}</Text>
      </Text>
      <Box marginTop={1}>
        <Text color={colors.text.secondary}>Obsidian vault (NTRP_VAULT_PATH)</Text>
      </Box>
    </Box>
  );
}
