import { createContext, useContext, useId, type ReactNode } from "react";
import { motion, useReducedMotion } from "motion/react";
import clsx from "clsx";
import { SPRING_LAYOUT } from "@/lib/tokens/motion";

// "plain" = no animated indicator; the active state is the item's own static
// tint (matches the app's tint-only vertical menus, no out-of-place slide).
type Variant = "underline" | "pill" | "plain";
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

  // APG tabs pattern: arrow keys (orientation-aware) + Home/End move between
  // tabs with automatic activation; roving tabindex keeps only the selected
  // tab in the Tab sequence.
  const onKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>) => {
    const horizontal = ctx.orientation === "horizontal";
    const nextKey = horizontal ? "ArrowRight" : "ArrowDown";
    const prevKey = horizontal ? "ArrowLeft" : "ArrowUp";
    if (![nextKey, prevKey, "Home", "End"].includes(e.key)) return;
    const tablist = e.currentTarget.closest('[role="tablist"]');
    if (!tablist) return;
    const tabs = Array.from(
      tablist.querySelectorAll<HTMLButtonElement>('[role="tab"]:not([disabled])'),
    );
    const idx = tabs.indexOf(e.currentTarget);
    if (idx === -1) return;
    e.preventDefault();
    const next =
      e.key === "Home" ? 0
      : e.key === "End" ? tabs.length - 1
      : e.key === nextKey ? (idx + 1) % tabs.length
      : (idx - 1 + tabs.length) % tabs.length;
    const target = tabs[next];
    target.focus();
    const nextValue = target.getAttribute("data-tab-value");
    if (nextValue !== null) ctx.onChange(nextValue);
  };

  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      tabIndex={active ? 0 : -1}
      data-active={active ? "true" : undefined}
      data-tab-value={value}
      onClick={() => ctx.onChange(value)}
      onKeyDown={onKeyDown}
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
