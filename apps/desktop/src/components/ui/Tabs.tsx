import { createContext, useContext, useId, type ReactNode } from "react";
import { motion, useReducedMotion } from "motion/react";
import clsx from "clsx";
import { SPRING_LAYOUT } from "../../lib/tokens/motion";

type Variant = "underline" | "pill";
type Orientation = "horizontal" | "vertical";

interface TabsContextValue {
  value: string;
  onChange: (value: string) => void;
  variant: Variant;
  orientation: Orientation;
  layoutId: string;
  indicatorClassName?: string;
  reduced: boolean;
}

const TabsContext = createContext<TabsContextValue | null>(null);

function useTabsContext(): TabsContextValue {
  const ctx = useContext(TabsContext);
  if (!ctx) throw new Error("<Tab> must be used inside <Tabs>");
  return ctx;
}

export function Tabs({
  value,
  onChange,
  variant = "underline",
  orientation = "horizontal",
  indicatorClassName,
  className,
  children,
}: {
  value: string;
  onChange: (value: string) => void;
  variant?: Variant;
  orientation?: Orientation;
  indicatorClassName?: string;
  className?: string;
  children: ReactNode;
}) {
  const layoutId = useId();
  const reduced = !!useReducedMotion();
  return (
    <TabsContext.Provider
      value={{ value, onChange, variant, orientation, layoutId, indicatorClassName, reduced }}
    >
      <div
        role="tablist"
        aria-orientation={orientation}
        className={clsx("flex", orientation === "vertical" && "flex-col", className)}
      >
        {children}
      </div>
    </TabsContext.Provider>
  );
}

export function Tab({
  value,
  className,
  children,
}: {
  value: string;
  className?: string;
  children: ReactNode;
}) {
  const ctx = useTabsContext();
  const active = ctx.value === value;
  const transition = ctx.reduced ? { layout: { duration: 0 } } : { layout: SPRING_LAYOUT };

  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      data-active={active ? "true" : undefined}
      onClick={() => ctx.onChange(value)}
      className={clsx("group relative isolate", className)}
    >
      {active && ctx.variant === "pill" && (
        <motion.span
          layoutId={`${ctx.layoutId}-indicator`}
          data-tab-indicator="pill"
          transition={transition}
          className={clsx(
            "absolute inset-0 -z-10 rounded-lg",
            ctx.indicatorClassName ??
              "bg-surface-soft shadow-[inset_0_0_0_1px_var(--color-line-soft)]",
          )}
        />
      )}
      {children}
      {active && ctx.variant === "underline" && (
        <motion.span
          layoutId={`${ctx.layoutId}-indicator`}
          data-tab-indicator="underline"
          transition={transition}
          className="absolute -bottom-px left-0 right-0 z-10 h-[2px] rounded-full bg-ink"
        />
      )}
    </button>
  );
}
