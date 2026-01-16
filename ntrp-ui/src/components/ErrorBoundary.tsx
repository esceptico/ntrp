import React, { Component, type ReactNode, type ErrorInfo } from "react";
import { Box, Text } from "ink";
import { colors } from "./ui/colors.js";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    this.props.onError?.(error, errorInfo);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      const errorMsg = this.state.error?.message || "Unknown error";
      return (
        <Box flexDirection="column" marginY={1} overflow="hidden">
          <Text color={colors.status.error} bold>Something went wrong</Text>
          <Text color={colors.text.muted} wrap="truncate">{errorMsg}</Text>
        </Box>
      );
    }

    return this.props.children;
  }
}
