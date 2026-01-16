import React from "react";
import { Box, Text } from "ink";
import { colors } from "./colors.js";

interface KeyValueProps {
  label: string;
  value: React.ReactNode;
  labelWidth?: number;
  valueColor?: string;
}

export function KeyValue({ label, value, labelWidth = 16, valueColor }: KeyValueProps) {
  const paddedLabel = label.padEnd(labelWidth);

  if (typeof value === 'string') {
    return (
      <Text>
        <Text color={colors.keyValue.label}>{paddedLabel}</Text>
        <Text color={valueColor || colors.keyValue.value}>{value}</Text>
      </Text>
    );
  }

  return (
    <Box>
      <Box width={labelWidth} flexShrink={0}>
        <Text color={colors.keyValue.label}>{label}</Text>
      </Box>
      {value}
    </Box>
  );
}
