import React from "react";
import { Text } from "ink";
import { colors } from "./colors.js";
import { Panel } from "./layout/Panel.js";

interface LoadingProps {
  message?: string;
}

export function Loading({ message = "Loading..." }: LoadingProps) {
  return (
    <Panel>
      <Text color={colors.text.muted}>{message}</Text>
    </Panel>
  );
}
