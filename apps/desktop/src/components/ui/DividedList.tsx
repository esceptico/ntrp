import type { ReactNode, Ref } from "react";
import clsx from "clsx";

/** Bordered, rounded list shell with hairline row separators. Rows are <li>
 *  children supplying their own padding. Shared by the settings tools list and
 *  the MCP server/tools sections. `className` carries per-site extras
 *  (e.g. `min-w-0 overflow-hidden`); override the default radius with the
 *  `!` modifier (e.g. `!rounded-md`) so it wins the Tailwind v4 cascade. */
export function DividedList({
  children,
  className,
  ref,
}: {
  children: ReactNode;
  className?: string;
  ref?: Ref<HTMLUListElement>;
}) {
  return (
    <ul
      ref={ref}
      className={clsx(
        "rounded-[10px] border border-line-soft bg-bg-main/30 divide-y divide-line-soft m-0 p-0 list-none",
        className,
      )}
    >
      {children}
    </ul>
  );
}
