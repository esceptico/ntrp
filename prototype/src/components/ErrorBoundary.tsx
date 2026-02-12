import { Component, createElement, type ReactNode, type ErrorInfo } from "react";
import { colors } from "./ui/colors.js";

interface Props {
  children?: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

class ErrorBoundaryClass extends Component<Props, State> {
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
        <box flexDirection="column" marginY={1} overflow="hidden">
          <text><span fg={colors.status.error}><strong>Something went wrong</strong></span></text>
          <text><span fg={colors.text.muted}>{errorMsg}</span></text>
        </box>
      );
    }

    return this.props.children;
  }
}

// Wrapper: OpenTUI's JSX types don't match React class components
export function ErrorBoundary({ children, fallback, onError }: Props) {
  return createElement(ErrorBoundaryClass, { fallback, onError }, children);
}
