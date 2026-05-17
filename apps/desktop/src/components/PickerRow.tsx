import { type ButtonHTMLAttributes, type ReactNode, type Ref } from "react";
import clsx from "clsx";

interface PickerRowProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  active: boolean;
  children: ReactNode;
  ref?: Ref<HTMLButtonElement>;
}

/** A row in a keyboard-driven list. Carries `data-active` for CSS, uses
 *  `onMouseMove` (NOT `onMouseEnter`) for hover-to-activate so the mouse
 *  doesn't fight the keyboard during scroll. Consumers style via the
 *  passed `className` and `data-active` attribute. */
export function PickerRow({ active, children, className, onMouseMove, ...rest }: PickerRowProps) {
  return (
    <button
      type="button"
      data-active={active || undefined}
      className={clsx("w-full text-left", className)}
      onMouseMove={onMouseMove}
      {...rest}
    >
      {children}
    </button>
  );
}
