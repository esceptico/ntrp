import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import clsx from "clsx";

type IconButtonSize = "xs" | "sm" | "md" | "lg";
type IconButtonTone = "muted" | "faint";

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  /** xs=22 (tight inline rows), sm=24, md=28 (default — headers/toolbars),
   *  lg=32 (prominent). Square; pick by role, not pixel. */
  size?: IconButtonSize;
  /** Resting icon color. `muted` (default) or quieter `faint`. */
  tone?: IconButtonTone;
  /** Hover resolves to destructive instead of ink. */
  danger?: boolean;
}

const SIZE: Record<IconButtonSize, string> = {
  xs: "w-[22px] h-[22px] rounded-[5px]",
  sm: "w-6 h-6 rounded-md",
  md: "w-7 h-7 rounded-md",
  lg: "w-8 h-8 rounded-md",
};

const TONE: Record<IconButtonTone, string> = {
  muted: "text-muted",
  faint: "text-faint",
};

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  function IconButton(
    { className, size = "md", tone = "muted", danger = false, type, children, ...rest },
    ref,
  ) {
    return (
      <button
        ref={ref}
        type={type ?? "button"}
        className={clsx(
          "grid place-items-center transition-colors hover:bg-surface-soft",
          "disabled:opacity-40 disabled:cursor-not-allowed",
          TONE[tone],
          danger ? "hover:text-bad" : "hover:text-ink",
          SIZE[size],
          className,
        )}
        {...rest}
      >
        {children}
      </button>
    );
  },
);
