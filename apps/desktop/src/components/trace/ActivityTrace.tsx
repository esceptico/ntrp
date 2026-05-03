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
  const visible = max != null ? items.slice(-max) : items;
  const targetHeight = max != null ? `${max * ROW_HEIGHT_EM}em` : "auto";

  return (
    <motion.div
      initial={false}
      animate={{
        height: collapsed ? 0 : targetHeight,
        opacity: collapsed ? 0 : 1,
      }}
      transition={{ duration: 0.22, ease: EASE }}
      style={{ overflow: "hidden" }}
      className="pl-4 mt-0.5"
    >
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
    </motion.div>
  );
}
