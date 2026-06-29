import clsx from "clsx";
import type { CSSProperties, ReactNode } from "react";

/**
 * One step in a vertical "thinking" timeline (after Fluid Functionalism's
 * thinking-steps): a left gutter with a semantic `node` (icon / dot) at the
 * top, threaded downward by a connector line, and the step content to its
 * right. Built from spans so it stays valid inside a `<button>`.
 *
 * The connector is drawn BELOW the node and hidden on the last step — so it
 * meets the next step's node with no dangling end and needs no cross-row
 * coordination (survives the live trace's row mount/unmount). One unified
 * treatment everywhere: the node tops the row, content (label + optional
 * description + chips) stacks to its right.
 */
export function ThinkingStep({
  node,
  last = false,
  className,
  style,
  children,
}: {
  node: ReactNode;
  last?: boolean;
  className?: string;
  style?: CSSProperties;
  children: ReactNode;
}) {
  return (
    <span className={clsx("flex w-full items-start gap-2.5", className)} style={style}>
      <span className="flex flex-col items-center shrink-0 self-stretch w-4">
        <span className="grid place-items-center pt-px text-muted">{node}</span>
        {!last && <span aria-hidden className="flex-1 w-px mt-1 bg-line/70" />}
      </span>
      <span className="flex min-w-0 flex-1 flex-col">{children}</span>
    </span>
  );
}
