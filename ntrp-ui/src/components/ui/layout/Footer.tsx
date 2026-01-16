import React from "react";
import { Box, Text } from "ink";
import { colors } from "../colors.js";

interface FooterProps {
  children: React.ReactNode;
  right?: React.ReactNode;
}

export function Footer({ children, right }: FooterProps) {
  return (
    <Box marginTop={1} justifyContent="space-between">
      <Text color={colors.footer}>{children}</Text>
      {right && <Text color={colors.footer}>{right}</Text>}
    </Box>
  );
}
