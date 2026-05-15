import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import clsx from "clsx";

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  /** 22px (sm) for inline-with-text rows, 26px (md, default) for modal/sidebar
   *  headers. Sizes match what existed across the codebase before extraction. */
  size?: "sm" | "md";
}

const SIZE = {
  sm: "w-[22px] h-[22px] rounded-[5px]",
  md: "w-[26px] h-[26px] rounded-md",
} as const;

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  function IconButton({ className, size = "md", type, children, ...rest }, ref) {
    return (
      <button
        ref={ref}
        type={type ?? "button"}
        className={clsx(
          "grid place-items-center text-muted hover:bg-surface-soft hover:text-ink transition-colors",
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
