import {
  forwardRef,
  type ButtonHTMLAttributes,
  type ReactNode,
} from "react";
import clsx from "clsx";
import { type LucideIcon } from "lucide-react";

/**
 * Text button primitive — sibling to {@link IconButton}. Collapses the
 * recurring inlined `<button>` patterns (primary / secondary / ghost) onto
 * one component so every action button shares the same height, radius,
 * motion, and disabled treatment. For icon-only controls use IconButton.
 *
 * Variants reproduce the existing hand-rolled classes 1:1, so swapping an
 * inlined button for `<Button>` is visually a no-op.
 *   primary   — solid ink slab (the main CTA: "New", "Save & reconnect")
 *   secondary — bordered, quiet fill on hover (neutral secondary action)
 *   ghost     — text-only, tints on hover (low-emphasis / inline action)
 *   danger    — destructive text, bad-tinted hover
 */
type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  /** sm = h-7 (dense toolbars/rows), md = h-8 (default, forms/modals). */
  size?: ButtonSize;
  leadingIcon?: LucideIcon;
  trailingIcon?: LucideIcon;
  /** Force the pressed/engaged look — e.g. while this button's menu is open. */
  active?: boolean;
  children?: ReactNode;
}

const BASE =
  "inline-flex items-center justify-center gap-1.5 rounded-md font-medium tracking-[-0.005em] " +
  "transition-[background-color,border-color,color,opacity,scale] duration-check ease-out " +
  "active:scale-[0.97] disabled:opacity-[0.45] disabled:cursor-not-allowed disabled:active:scale-100";

const SIZE: Record<ButtonSize, string> = {
  sm: "h-7 px-2.5 text-sm",
  md: "h-8 px-3 text-sm",
};

const ICON_PX: Record<ButtonSize, number> = { sm: 14, md: 16 };

const VARIANT: Record<ButtonVariant, string> = {
  primary: "bg-ink text-on-ink hover:opacity-90",
  secondary:
    "border border-line-soft text-ink-soft hover:bg-surface-soft hover:border-line-strong",
  ghost: "text-muted hover:text-ink hover:bg-surface-soft",
  danger: "text-bad hover:bg-bad-soft",
};

const ACTIVE: Record<ButtonVariant, string> = {
  primary: "opacity-90",
  secondary: "bg-surface-soft border-line-strong",
  ghost: "text-ink bg-surface-soft",
  danger: "bg-bad-soft",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "primary",
    size = "md",
    leadingIcon: Leading,
    trailingIcon: Trailing,
    active = false,
    type,
    className,
    children,
    ...rest
  },
  ref,
) {
  const px = ICON_PX[size];
  return (
    <button
      ref={ref}
      type={type ?? "button"}
      data-active={active || undefined}
      className={clsx(BASE, SIZE[size], VARIANT[variant], active && ACTIVE[variant], className)}
      {...rest}
    >
      {Leading && <Leading size={px} strokeWidth={2} className="shrink-0" />}
      {children}
      {Trailing && <Trailing size={px} strokeWidth={2} className="shrink-0" />}
    </button>
  );
});
