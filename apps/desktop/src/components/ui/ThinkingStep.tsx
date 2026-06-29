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
 * coordination (survives the live trace's row mount/unmount). `align="center"`
 * is the compact single-line live tail; `align="start"` is the rich,
 * multi-line settled view (label + description + chips).
 */
export function ThinkingStep({
  node,
  last = false,
  align = "start",
  className,
  style,
  children,
}: {
  node: ReactNode;
  last?: boolean;
  align?: "start" | "center";
  className?: string;
  style?: CSSProperties;
  children: ReactNode;
}) {
  return (
    <span
      className={clsx("flex w-full gap-2.5", align === "center" ? "items-center" : "items-start", className)}
      style={style}
    >
      <span className="flex flex-col items-center shrink-0 self-stretch w-4">
        <span className="grid place-items-center pt-px text-muted">{node}</span>
        {!last && <span aria-hidden className="flex-1 w-px mt-1 bg-line" />}
      </span>
      <span className="min-w-0 flex-1">{children}</span>
    </span>
  );
}
