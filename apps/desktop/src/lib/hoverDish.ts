import type { MouseEvent as ReactMouseEvent } from "react";

/**
 * Mousemove handler that writes the cursor's element-local position into
 * CSS custom properties `--mx` / `--my`, used by the `.hover-dish` rule
 * in styles.css to render a soft radial gradient that follows the
 * cursor on hover. Apply with `onMouseMove={trackHoverDish}` on any row
 * that has `className="hover-dish ..."`.
 */
export function trackHoverDish(event: ReactMouseEvent<HTMLElement>): void {
  const target = event.currentTarget;
  const rect = target.getBoundingClientRect();
  target.style.setProperty("--mx", `${event.clientX - rect.left}px`);
  target.style.setProperty("--my", `${event.clientY - rect.top}px`);
}
