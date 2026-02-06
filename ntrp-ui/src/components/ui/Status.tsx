import React from "react";
import { Text } from "ink";
import { colors } from "./colors.js";
import { BULLET } from "../../lib/constants.js";
import { Panel } from "./layout/Panel.js";

// StatusIndicator - Colored dot with label

interface StatusIndicatorProps {
  status: "connected" | "disconnected" | "error" | "warning" | "running" | "pending";
  label: string;
  detail?: string;
}

export function StatusIndicator({ status, label, detail }: StatusIndicatorProps) {
  const statusColors: Record<StatusIndicatorProps["status"], string> = {
    connected: colors.status.success,
    disconnected: colors.text.muted,
    error: colors.status.error,
    warning: colors.status.warning,
    running: colors.status.warning,
    pending: colors.text.secondary,
  };
  const icons: Record<StatusIndicatorProps["status"], string> = {
    connected: BULLET,
    disconnected: "○",
    error: "✗",
    warning: BULLET,
    running: "◐",
    pending: "○",
  };

  const color = statusColors[status];
  const icon = icons[status];

  return (
    <Text>
      <Text color={color}>{icon}</Text>
      <Text color={status === "disconnected" ? colors.text.muted : colors.text.primary}>
        {" "}{label}
      </Text>
      {detail && <Text color={colors.text.secondary}> {detail}</Text>}
    </Text>
  );
}

// Badge - Small status tag

interface BadgeProps {
  children: React.ReactNode;
  color?: string;
  dim?: boolean;
}

export function Badge({ children, color, dim = false }: BadgeProps) {
  return (
    <Text color={color || colors.text.secondary} dimColor={dim}>
      [{children}]
    </Text>
  );
}

// Loading - Loading state

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

// ErrorDisplay - Error state

interface ErrorDisplayProps {
  message: string;
}

export function ErrorDisplay({ message }: ErrorDisplayProps) {
  return (
    <Panel>
      <Text color={colors.status.error}>{message}</Text>
    </Panel>
  );
}
