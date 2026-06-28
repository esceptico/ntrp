import clsx from "clsx";
import type { CSSProperties, ReactNode } from "react";

/**
 * One step in a vertical "thinking" timeline: a left gutter carrying a node
 * (status dot / glyph) threaded by a continuous spine, and the step content to
 * its right. Built from spans so it stays valid inside a `<button>` (the tool
 * row is one click target).
 *
 * The spine is drawn per-row (full gutter height) and trimmed to the node
 * centre on the first/last step so it never dangles past the timeline ends —
 * which also means it survives the live trace's row mount/unmount without any
 * cross-row coordination. The opaque node covers the 1px line where they meet.
 */
export function ThinkingStep({
  node,
  first = false,
  last = false,
  className,
  style,
  children,
}: {
  node: ReactNode;
  first?: boolean;
  last?: boolean;
  className?: string;
  style?: CSSProperties;
  children: ReactNode;
}) {
  return (
    <span className={clsx("flex h-full min-w-0 items-center gap-2", className)} style={style}>
      <span className="relative h-full w-[18px] shrink-0">
        <span
          aria-hidden
          className="thinking-spine"
          style={{ top: first ? "50%" : 0, bottom: last ? "50%" : 0 }}
        />
        <span className="thinking-node">{node}</span>
      </span>
      <span className="flex min-w-0 flex-1 items-center gap-2">{children}</span>
    </span>
  );
}
