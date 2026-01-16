import React from "react";
import { Text } from "ink";
import { useContentWidth } from "../../../contexts/index.js";
import { colors } from "../colors.js";

interface DividerProps {
  width?: number;
}

export function Divider({ width }: DividerProps) {
  const contentWidth = useContentWidth();
  const lineWidth = width ?? Math.min(contentWidth - 2, 60);
  const line = "─".repeat(Math.max(0, lineWidth));

  return <Text color={colors.divider}>{line}</Text>;
}
