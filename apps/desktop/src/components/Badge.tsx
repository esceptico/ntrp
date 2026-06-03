import type { CSSProperties, ReactNode, Ref } from "react";
import clsx from "clsx";

export type BadgeTone = "neutral" | "accent" | "ok" | "warn" | "bad";

interface BadgeProps {
  children: ReactNode;
  tone?: BadgeTone;
  size?: "sm" | "md";
  shape?: "pill" | "rounded";
  outline?: boolean;
  leading?: ReactNode;
  className?: string;
  style?: CSSProperties;
  title?: string;
  ref?: Ref<HTMLSpanElement>;
}

const toneFill: Record<BadgeTone, string> = {
  neutral: "bg-surface-sunken text-muted",
  accent: "bg-accent-soft text-accent-strong",
  ok: "bg-ok-soft text-ok",
  warn: "bg-warn-soft text-warn",
  bad: "bg-bad-soft text-bad",
};

const toneBorder: Record<BadgeTone, string> = {
  neutral: "border-line-soft",
  accent: "border-accent/15",
  ok: "border-ok/20",
  warn: "border-warn/20",
  bad: "border-bad/20",
};

const sizeClass = {
  sm: "px-1.5 h-[18px] text-2xs",
  md: "px-2 py-[3px] text-xs",
};

export function Badge({
  children,
  tone = "neutral",
  size = "sm",
  shape = "pill",
  outline = false,
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
        "inline-flex max-w-full shrink-0 justify-self-start items-center gap-1 font-medium tracking-[0.005em] whitespace-nowrap",
        shape === "pill" ? "rounded-full" : "rounded-md",
        sizeClass[size],
        toneFill[tone],
        outline && ["border", toneBorder[tone]],
        className,
      )}
    >
      {leading != null && <span className="inline-flex shrink-0">{leading}</span>}
      {children}
    </span>
  );
}
