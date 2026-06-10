import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** Optional override for the fallback UI. Receives the caught error
   *  and a `reset` callback that re-mounts the children. */
  fallback?: (error: Error, reset: () => void) => ReactNode;
}

interface State {
  error: Error | null;
}

/** Last-resort safety net so a thrown render error doesn't unmount the
 *  entire app tree. Wrap subtrees that can recover independently
 *  (Chat/Messages, the Suspense'd modals, etc.) so one bad render
 *  doesn't black out the shell. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Surface to devtools console; production logging hook can attach
    // here later (Sentry/etc).
    console.error("[ntrp] render error caught by ErrorBoundary", error, info);
  }

  reset = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;
    if (this.props.fallback) return this.props.fallback(error, this.reset);
    return <DefaultFallback error={error} onReset={this.reset} />;
  }
}

function DefaultFallback({ error, onReset }: { error: Error; onReset: () => void }) {
  return (
    <div className="absolute inset-0 grid place-items-center p-8">
      <div className="surface-panel surface-radius-md max-w-[480px] p-6">
        <div className="text-lg font-semibold tracking-[-0.012em] text-ink">
          Something went wrong rendering this view.
        </div>
        <div className="mt-2 text-sm text-muted">
          The rest of the app is still running. You can try again, or reload
          the window if it keeps happening.
        </div>
        <pre className="mt-3 text-xs text-faint font-mono whitespace-pre-wrap break-words max-h-32 overflow-auto">
          {error.message}
        </pre>
        <div className="mt-4 flex items-center gap-2">
          <button
            type="button"
            onClick={onReset}
            className="inline-flex items-center gap-1.5 h-7 px-3 rounded-md bg-ink text-on-ink text-sm font-medium hover:opacity-90 transition-[opacity,scale] duration-check ease-out active:scale-[0.97]"
          >
            Try again
          </button>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="inline-flex items-center gap-1.5 h-7 px-3 rounded-md text-sm font-medium text-muted hover:bg-surface-soft hover:text-ink transition-[background-color,color,scale] duration-check ease-out active:scale-[0.97]"
          >
            Reload window
          </button>
        </div>
      </div>
    </div>
  );
}
