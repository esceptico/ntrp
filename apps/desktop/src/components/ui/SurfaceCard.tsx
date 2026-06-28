import { motion } from "motion/react";
import clsx from "clsx";
import type { ReactNode } from "react";
import { SPRING_LAYOUT, ROW_EXIT, EASE_OUT, MOTION } from "@/lib/tokens/motion";

const SURFACES = { div: motion.div, article: motion.article } as const;

interface SurfaceCardProps {
  /** Wraps the body with a stretched, accessible click target. */
  interactive?: boolean;
  onClick?: () => void;
  /** Accessible name for the stretched click target (required when interactive). */
  ariaLabel?: string;
  /** Surface radius token. Defaults to the small list-item card radius. */
  radius?: "sm" | "md" | "lg";
  /** Semantic element for the surface. */
  as?: "div" | "article";
  className?: string;
  children: ReactNode;
  /** Forwarded onto the surface element (e.g. `data-suggestion` test hooks). */
  [dataAttr: `data-${string}`]: string | undefined;
}

/**
 * Shared shell for the interactive automation cards (SuggestionCard,
 * AutomationCard): a `surface-panel` surface with the house layout/enter/exit
 * motion, plus the stretched accessible click-target pattern they duplicated.
 *
 * When `interactive`, a real `<button>` is painted over the whole card as a
 * direct child (keyboard + screen-reader friendly) BELOW the body. Card bodies
 * lift their own interactive controls above it with `relative z-[1]` / absolute
 * so each stays independently clickable. The press-scale is scoped to the
 * card's own direct-child buttons (`>button:active`) so a nested control press
 * doesn't shrink the whole card.
 */
export function SurfaceCard({
  interactive = false,
  onClick,
  ariaLabel,
  radius = "sm",
  as = "div",
  className,
  children,
  ...dataAttrs
}: SurfaceCardProps) {
  const Surface = SURFACES[as];
  return (
    <Surface
      {...dataAttrs}
      layout
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ ...ROW_EXIT, transition: { duration: MOTION.row, ease: EASE_OUT } }}
      transition={SPRING_LAYOUT}
      className={clsx(
        "surface-panel relative focus-within:shadow-[0_0_0_3px_var(--color-accent-soft)]",
        `surface-radius-${radius}`,
        interactive &&
          "transition-[scale] duration-check ease-out has-[>button:active]:scale-[0.99]",
        className,
      )}
    >
      {interactive && onClick && (
        <button
          type="button"
          aria-label={ariaLabel}
          onClick={onClick}
          className="absolute inset-0 cursor-pointer rounded-[inherit] focus:outline-none"
        />
      )}
      {children}
    </Surface>
  );
}
