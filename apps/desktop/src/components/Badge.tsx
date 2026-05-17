import type { CSSProperties, ReactNode, Ref } from "react";
import clsx from "clsx";

export type BadgeTone = "neutral" | "accent" | "ok" | "warn" | "bad";

interface BadgeProps {
  children: ReactNode;
  tone?: BadgeTone;
  leading?: ReactNode;
  className?: string;
  style?: CSSProperties;
  title?: string;
  ref?: Ref<HTMLSpanElement>;
}

const toneClass: Record<BadgeTone, string> = {
  neutral: "bg-surface-sunken text-muted",
  accent: "bg-accent-soft text-accent-strong",
  ok: "bg-ok-soft text-ok",
  warn: "bg-warn-soft text-warn",
  bad: "bg-bad-soft text-bad",
};

export function Badge({
  children,
  tone = "neutral",
  leading,
  className,
  style,
  title,
  ref,
}: BadgeProps) {
  return (
    <span
      ref={ref}
      style={style}
      title={title}
      className={clsx(
        "inline-flex max-w-full shrink-0 items-center gap-1 px-1.5 h-[18px] rounded-full text-2xs font-medium tracking-[0.005em] whitespace-nowrap",
        toneClass[tone],
        className,
      )}
    >
      {leading != null && <span className="inline-flex shrink-0">{leading}</span>}
      {children}
    </span>
  );
}
