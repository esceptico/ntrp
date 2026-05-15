import { useStore } from "../../store";

function formatTokens(n: number): string {
  if (n < 1000) return `${n}`;
  if (n < 10000) return `${(n / 1000).toFixed(1)}k`;
  return `${Math.round(n / 1000)}k`;
}

function formatCost(n: number): string {
  return n < 0.01 ? `$${n.toFixed(4)}` : `$${n.toFixed(3)}`;
}

/** Inline composer-toolbar pill showing the last prompt's context size and
 *  cumulative session cost. Renders nothing when both values are zero. */
export function UsageDisplay() {
  const usage = useStore((s) => s.usage);
  if (!usage.lastPrompt && !usage.totalCost) return <span />;
  return (
    <span className="px-1.5 text-xs text-faint tabular-nums tracking-[-0.005em] select-none">
      {usage.lastPrompt > 0 && (
        <>
          <strong className="text-muted font-medium">{formatTokens(usage.lastPrompt)}</strong> ctx
        </>
      )}
      {usage.totalCost > 0 && (
        <>
          {usage.lastPrompt > 0 && " · "}
          {formatCost(usage.totalCost)}
        </>
      )}
    </span>
  );
}
