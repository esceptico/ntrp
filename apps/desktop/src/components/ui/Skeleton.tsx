import clsx from "clsx";

interface SkeletonProps {
  width?: number | string;
  height?: number | string;
  radius?: number;
  className?: string;
  /** When > 1, render that many stacked bars (last ~70% width). */
  lines?: number;
}

/**
 * Loading placeholder. Thin wrapper over the house `.skeleton` class
 * (styles.css) — its sweep runs as a CSS animation, off the main thread, so
 * it stays smooth while the page is busy loading the data it's standing in
 * for. Honors reduced-motion via the global stylesheet.
 */
export function Skeleton({ width = "100%", height = "1rem", radius, className, lines = 1 }: SkeletonProps) {
  const bar = (key: number, w: number | string) => (
    <div
      key={key}
      className={clsx("skeleton", className)}
      style={{ width: w, height, ...(radius != null ? { borderRadius: radius } : null) }}
    />
  );

  if (lines <= 1) return bar(0, width);

  return (
    <div className="flex flex-col gap-2">
      {Array.from({ length: lines }, (_, i) => bar(i, i === lines - 1 ? "70%" : width))}
    </div>
  );
}
