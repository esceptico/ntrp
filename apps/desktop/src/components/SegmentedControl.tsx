import { CSSProperties, KeyboardEvent, ReactNode, Ref, useId, useRef } from "react";
import { motion, useReducedMotion } from "motion/react";
import { SPRING_LAYOUT } from "../lib/tokens/motion";

type Option = string | { value: string; label: string; icon?: ReactNode };

interface Props {
  options: Option[];
  value: string;
  onChange: (value: string) => void;
  size?: "sm" | "md" | "lg";
  className?: string;
  ref?: Ref<HTMLDivElement>;
}

type NormalizedOption = { value: string; label: string; icon?: ReactNode };

const SIZES = {
  sm: { pad: 4, h: 32, font: 12, gap: 2, padX: 14 },
  md: { pad: 5, h: 40, font: 13, gap: 3, padX: 18 },
  lg: { pad: 6, h: 48, font: 14, gap: 4, padX: 22 },
} as const;

// The pill reads better slightly larger than the button it highlights.
const PILL_GROW = 2;

const BTN_STYLE_BASE: CSSProperties = {
  position: "relative",
  isolation: "isolate",
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  gap: 6,
  lineHeight: 1,
  background: "transparent",
  border: "none",
  borderRadius: 999,
  cursor: "pointer",
  appearance: "none",
  WebkitAppearance: "none",
  transition: "color var(--duration-trace) var(--ease-out-soft)",
  userSelect: "none",
};

function normalize(opt: Option): NormalizedOption {
  return typeof opt === "string" ? { value: opt, label: opt } : opt;
}

export function SegmentedControl({
  options,
  value,
  onChange,
  size = "md",
  className,
  ref,
}: Props) {
  const items = options.map(normalize);
  const sz = SIZES[size];

  const layoutId = useId();
  const reduced = !!useReducedMotion();
  const btnRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const activeIndex = items.findIndex((o) => o.value === value);

  const focusAt = (i: number) => {
    const next = (i + items.length) % items.length;
    btnRefs.current[next]?.focus();
    if (items[next].value !== value) onChange(items[next].value);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "ArrowRight") {
      e.preventDefault();
      focusAt(activeIndex + 1);
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      focusAt(activeIndex - 1);
    } else if (e.key === "Home") {
      e.preventDefault();
      focusAt(0);
    } else if (e.key === "End") {
      e.preventDefault();
      focusAt(items.length - 1);
    }
  };

  const trackStyle: CSSProperties = {
    position: "relative",
    display: "inline-flex",
    // Buttons stretch to the pill's vertical bounds: the track's vertical
    // padding doubles as the pill inset, so the layoutId indicator inside
    // the active button needs no measurement.
    alignItems: "stretch",
    gap: sz.gap,
    height: sz.h,
    padding: `${Math.max(2, sz.pad - PILL_GROW)}px ${sz.pad}px`,
    borderRadius: 999,
    background: "var(--gt-track-bg)",
    border: "1px solid var(--gt-track-border)",
    boxShadow: "var(--gt-track-shadow)",
  };

  const pillStyle: CSSProperties = {
    position: "absolute",
    top: 0,
    bottom: 0,
    left: -PILL_GROW,
    right: -PILL_GROW,
    zIndex: -1,
    borderRadius: 999,
    background: "var(--gt-pill-bg)",
    border: "1px solid var(--gt-pill-border)",
    boxShadow: "var(--gt-pill-shadow)",
    pointerEvents: "none",
  };

  const classes = ["segmented-control", className].filter(Boolean).join(" ");

  const btnSizing: CSSProperties = {
    padding: `0 ${sz.padX}px`,
    fontSize: sz.font,
  };

  return (
    <div
      ref={ref}
      role="tablist"
      className={classes}
      style={trackStyle}
      onKeyDown={onKeyDown}
    >
      {items.map((opt, i) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            ref={(el) => {
              btnRefs.current[i] = el;
            }}
            type="button"
            role="tab"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(opt.value)}
            style={{
              ...BTN_STYLE_BASE,
              ...btnSizing,
              fontWeight: active ? 600 : 500,
              color: active ? "var(--gt-fg)" : "var(--gt-fg-muted)",
            }}
          >
            {active && (
              <motion.span
                aria-hidden
                layoutId={`${layoutId}-pill`}
                className="segmented-control-pill"
                transition={reduced ? { layout: { duration: 0 } } : { layout: SPRING_LAYOUT }}
                style={pillStyle}
              />
            )}
            {opt.icon ? (
              <span style={{ display: "inline-flex" }}>{opt.icon}</span>
            ) : null}
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

export default SegmentedControl;
