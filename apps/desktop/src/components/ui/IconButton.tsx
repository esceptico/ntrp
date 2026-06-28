import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import clsx from "clsx";
import { Tooltip } from "@/components/ui/Tooltip";

type IconButtonSize = "xs" | "sm" | "md" | "lg";
type IconButtonTone = "muted" | "faint" | "primary";
type IconButtonShape = "square" | "circle";

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  /** xs=22 (tight inline rows), sm=24, md=28 (default — headers/toolbars),
   *  lg=32 (prominent). Pick by role, not pixel. */
  size?: IconButtonSize;
  /** Resting icon color. `muted` (default), quieter `faint`, or solid `primary`
   *  (ink slab — round send/accept buttons). */
  tone?: IconButtonTone;
  /** Corner radius. `square` (default — `rounded-md`) or `circle`
   *  (`rounded-full`, for solid round send/accept/dismiss buttons). */
  shape?: IconButtonShape;
  /** Hover resolves to destructive instead of ink. */
  danger?: boolean;
  /** Force the pressed/engaged look + sets aria-pressed (e.g. the deny-with-
   *  reason toggle, a filter trigger while its menu is open). */
  active?: boolean;
}

// Square radius scales with size; circle is always fully round.
const SIZE: Record<IconButtonSize, string> = {
  xs: "w-[22px] h-[22px]",
  sm: "w-6 h-6",
  md: "w-7 h-7",
  lg: "w-8 h-8",
};

const SQUARE_RADIUS: Record<IconButtonSize, string> = {
  xs: "rounded-[5px]",
  sm: "rounded-md",
  md: "rounded-md",
  lg: "rounded-md",
};

const TONE: Record<IconButtonTone, string> = {
  muted: "text-muted",
  faint: "text-faint",
  // Solid ink slab; opacity hover matches Button's `primary`.
  primary: "bg-ink text-on-ink hover:opacity-90",
};

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  function IconButton(
    {
      className,
      size = "md",
      tone = "muted",
      shape = "square",
      danger = false,
      active = false,
      type,
      children,
      title,
      ...rest
    },
    ref,
  ) {
    // `title` becomes an animated Tooltip instead of the OS bubble. The
    // Tooltip only wires aria-describedby while open, so an icon-only button
    // with just a `title` would otherwise have no accessible name — derive
    // one from the title. An explicit aria-label in `rest` still wins.
    const accessibleName =
      (rest["aria-label"] as string | undefined) ??
      (typeof title === "string" ? title : undefined);
    // The solid `primary` tone owns its full hover (opacity), so the
    // surface-soft fill + ink/bad text hover only apply to the flat tones.
    const isPrimary = tone === "primary";
    const button = (
      <button
        ref={ref}
        type={type ?? "button"}
        aria-label={accessibleName}
        aria-pressed={active || undefined}
        data-active={active || undefined}
        className={clsx(
          "grid place-items-center transition-[background-color,color,transform,scale] duration-check ease-out active:scale-[0.97]",
          "disabled:opacity-[0.45] disabled:cursor-not-allowed",
          TONE[tone],
          !isPrimary && [
            "hover:bg-surface-soft",
            danger ? "hover:text-bad" : "hover:text-ink",
            active && "bg-surface-soft text-ink",
          ],
          SIZE[size],
          shape === "circle" ? "rounded-full" : SQUARE_RADIUS[size],
          className,
        )}
        {...rest}
      >
        {children}
      </button>
    );
    return title ? <Tooltip label={title}>{button}</Tooltip> : button;
  },
);
