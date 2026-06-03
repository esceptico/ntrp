import {
  CSSProperties,
  KeyboardEvent,
  ReactNode,
  Ref,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

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

// Mirrors --ease-emphasized / EASE_EMPHASIZED — moving/morphing on-screen.
const EASE = "var(--ease-emphasized)";

const BTN_STYLE_BASE: CSSProperties = {
  position: "relative",
  zIndex: 1,
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
  transition: "color var(--duration-trace) ease",
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

  const trackRef = useRef<HTMLDivElement>(null);
  const btnRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const [pill, setPill] = useState<{ x: number; w: number } | null>(null);
  const [ready, setReady] = useState(false);

  const activeIndex = items.findIndex((o) => o.value === value);

  useLayoutEffect(() => {
    if (activeIndex === -1) {
      setPill(null);
      setReady(true);
      return;
    }
    const measure = () => {
      const btn = btnRefs.current[activeIndex];
      const track = trackRef.current;
      if (!btn || !track) return;

      // offset* is layout-space, unlike getBoundingClientRect(), which is
      // distorted while modals/popovers are animating scale transforms.
      setPill({ x: btn.offsetLeft, w: btn.offsetWidth });
    };

    measure();
    const readyId = requestAnimationFrame(() => setReady(true));
    const resizeObserver = new ResizeObserver(measure);
    const track = trackRef.current;
    if (track) resizeObserver.observe(track);
    for (const btn of btnRefs.current) {
      if (btn) resizeObserver.observe(btn);
    }
    return () => {
      cancelAnimationFrame(readyId);
      resizeObserver.disconnect();
    };
  }, [activeIndex, items.length]);

  const setRefs = (node: HTMLDivElement | null) => {
    trackRef.current = node;
    if (typeof ref === "function") ref(node);
    else if (ref) (ref as { current: HTMLDivElement | null }).current = node;
  };

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
    alignItems: "center",
    gap: sz.gap,
    height: sz.h,
    padding: sz.pad,
    borderRadius: 999,
    background: "var(--gt-track-bg)",
    border: "1px solid var(--gt-track-border)",
    boxShadow: "var(--gt-track-shadow)",
  };

  const pillGrow = 2;
  const pillStyle: CSSProperties = {
    position: "absolute",
    // top/bottom symmetric — explicit height + border-box + 1px border
    // gave a 2px vertical asymmetry (top gap > bottom gap).
    top: Math.max(2, sz.pad - pillGrow),
    bottom: Math.max(2, sz.pad - pillGrow),
    left: 0,
    width: pill ? pill.w + pillGrow * 2 : 0,
    transform: `translateX(${pill ? pill.x - pillGrow : 0}px)`,
    borderRadius: 999,
    background: "var(--gt-pill-bg)",
    border: "1px solid var(--gt-pill-border)",
    boxShadow: "var(--gt-pill-shadow)",
    transition: ready
      ? `transform var(--duration-panel) ${EASE}, width var(--duration-panel) ${EASE}`
      : "none",
    pointerEvents: "none",
    zIndex: 0,
    opacity: pill ? 1 : 0,
  };

  const classes = ["segmented-control", className].filter(Boolean).join(" ");

  const btnSizing: CSSProperties = {
    padding: `0 ${sz.padX}px`,
    fontSize: sz.font,
  };

  return (
    <div
      ref={setRefs}
      role="tablist"
      className={classes}
      style={trackStyle}
      onKeyDown={onKeyDown}
    >
      <span aria-hidden className="segmented-control-pill" style={pillStyle} />
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
