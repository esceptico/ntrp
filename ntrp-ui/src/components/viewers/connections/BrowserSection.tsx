import React from "react";
import { Box, Text } from "ink";
import type { ServerConfig } from "../../../api/client.js";
import { colors } from "../../ui/index.js";
import { BULLET } from "../../../lib/constants.js";

interface BrowserSectionProps {
  serverConfig: ServerConfig;
  width: number;
}

export function BrowserSection({ serverConfig, width }: BrowserSectionProps) {
  return (
    <Box flexDirection="column" marginY={1} width={width} overflow="hidden">
      <Text>
        <Text color={serverConfig.has_browser ? colors.status.success : colors.text.muted}>
          {serverConfig.has_browser ? BULLET : "○"}
        </Text>
        <Text color={serverConfig.has_browser ? colors.text.primary : colors.text.muted}>
          {" "}{serverConfig.has_browser ? `${serverConfig.browser} history` : "Not connected"}
        </Text>
        {!serverConfig.has_browser && <Text color={colors.text.secondary}> (set NTRP_BROWSER)</Text>}
      </Text>
    </Box>
  );
}
