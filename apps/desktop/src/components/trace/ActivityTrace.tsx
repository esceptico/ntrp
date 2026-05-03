import type { ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ChevronDown } from "lucide-react";
import clsx from "clsx";
import { RollingToken } from "./RollingToken";

const EASE = [0.32, 0.72, 0, 1] as const;
const ROW_HEIGHT_EM = 1.55;

export type ActivityItem = {
  id: string;
  kind: string;
  target: string;
};

export function ActivityTrace({ children }: { children: ReactNode }) {
  return (
    <motion.div
      layout
      transition={{ layout: { duration: 0.22, ease: EASE } }}
      className="font-sans text-[13px] leading-[1.55] text-muted"
    >
      {children}
    </motion.div>
  );
}

export function ActivityHeader({
  label,
  count,
  onToggle,
  expanded,
}: {
  label: string;
  count: number;
  onToggle?: () => void;
  expanded?: boolean;
}) {
  const word = count === 1 ? "tool" : "tools";
  const interactive = !!onToggle;

  return (
    <button
      type={interactive ? "button" : undefined}
      onClick={onToggle}
      disabled={!interactive}
      className={clsx(
        "flex items-baseline gap-1 m-0 p-0 bg-transparent border-0 text-left",
        interactive ? "cursor-pointer hover:opacity-70 select-none" : "cursor-default",
      )}
    >
      <span className="font-medium text-ink-soft mr-1.5">
        <RollingToken value={label} />
      </span>
      <span>
        <RollingToken value={String(count)} mono />
        {" "}
        <RollingToken value={word} />
      </span>
      {interactive && (
        <ChevronDown
          size={12}
          strokeWidth={2}
          className={clsx(
            "ml-1 self-center transition-transform duration-200 text-faint",
            expanded && "rotate-180",
          )}
        />
      )}
    </button>
  );
}

export function ActivityTail({
  items,
  max,
  collapsed = false,
}: {
  items: ActivityItem[];
  max?: number;
  collapsed?: boolean;
}) {
  // Two render modes:
  //   - "rolling" (max set): used live during a run. Keeps AnimatePresence so
  //     new items roll in and old ones fall off as the activity grows.
  //   - "static"  (max unset): used post-run when the user has clicked to
  //     expand the full list. No per-item entry animation — only the
  //     container's height animation handles the open/close transition.
  // Mixing the two caused items to "appear from the center" because the
  // older items (suddenly newly visible when expanding) ran their initial
  // y-translate animation while the container was also growing in height.
  const rolling = max != null;
  const visible = rolling ? items.slice(-max) : items;
  const targetHeight = rolling ? `${max * ROW_HEIGHT_EM}em` : "auto";

  return (
    <motion.div
      initial={false}
      animate={{
        height: collapsed ? 0 : targetHeight,
        opacity: collapsed ? 0 : 1,
      }}
      transition={{ duration: 0.24, ease: EASE }}
      style={{ overflow: "hidden" }}
      className="pl-4 mt-0.5"
    >
      {rolling ? (
        <AnimatePresence mode="popLayout" initial={false}>
          {visible.map((item) => (
            <motion.div
              key={item.id}
              layout
              initial={{ y: 8, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: -8, opacity: 0 }}
              transition={{ duration: 0.22, ease: EASE }}
              style={{ height: `${ROW_HEIGHT_EM}em` }}
              className="flex items-baseline min-w-0"
            >
              <span className="font-mono text-faint truncate">{item.target || item.kind}</span>
            </motion.div>
          ))}
        </AnimatePresence>
      ) : (
        visible.map((item) => (
          <div
            key={item.id}
            style={{ height: `${ROW_HEIGHT_EM}em` }}
            className="flex items-baseline min-w-0"
          >
            <span className="font-mono text-faint truncate">{item.target || item.kind}</span>
          </div>
        ))
      )}
    </motion.div>
  );
}
