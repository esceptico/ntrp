import {
  CSSProperties,
  ReactNode,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { GlassSurface } from "./GlassSurface";

type Option = string | { value: string; label: string; icon?: ReactNode };

interface Props {
  options: Option[];
  value: string;
  onChange: (value: string) => void;
  size?: "sm" | "md" | "lg";
  tone?: "light" | "dark" | "auto";
  /** Apply backdrop-filter to the track. Expensive in long lists — default off. */
  blur?: boolean;
}

type NormalizedOption = { value: string; label: string; icon?: ReactNode };

const SIZES = {
  sm: { height: 32, font: 12, padX: 14, gap: 4 },
  md: { height: 40, font: 13, padX: 16, gap: 4 },
  lg: { height: 48, font: 14, padX: 20, gap: 6 },
} as const;

const TONES = {
  light: {
    pill: "rgba(255,255,255,0.75)",
    textActive: "rgba(20,20,30,0.92)",
    textIdle: "rgba(20,20,30,0.55)",
    pillShadow: "0 1px 2px rgba(0,0,0,0.08), 0 4px 12px rgba(0,0,0,0.06)",
  },
  dark: {
    pill: "rgba(255,255,255,0.14)",
    textActive: "rgba(255,255,255,0.95)",
    textIdle: "rgba(255,255,255,0.55)",
    pillShadow: "0 1px 2px rgba(0,0,0,0.25)",
  },
  auto: {
    pill: "light-dark(rgba(255,255,255,0.75), rgba(255,255,255,0.14))",
    textActive: "light-dark(rgba(20,20,30,0.92), rgba(255,255,255,0.95))",
    textIdle: "light-dark(rgba(20,20,30,0.55), rgba(255,255,255,0.55))",
    pillShadow: "0 1px 2px rgba(0,0,0,0.15)",
  },
} as const;

const EASE = "cubic-bezier(0.32, 0.72, 0, 1)";

function normalize(opt: Option): NormalizedOption {
  return typeof opt === "string" ? { value: opt, label: opt } : opt;
}

export function GlassToggle({
  options,
  value,
  onChange,
  size = "md",
  tone = "auto",
  blur = false,
}: Props) {
  const items = options.map(normalize);
  const sz = SIZES[size];
  const t = TONES[tone];

  const trackRef = useRef<HTMLDivElement>(null);
  const btnRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const [pill, setPill] = useState<{ x: number; w: number } | null>(null);
  const [ready, setReady] = useState(false);

  useLayoutEffect(() => {
    const idx = items.findIndex((o) => o.value === value);
    const btn = btnRefs.current[idx];
    const track = trackRef.current;
    if (!btn || !track) return;
    const b = btn.getBoundingClientRect();
    const tr = track.getBoundingClientRect();
    setPill({ x: b.left - tr.left, w: b.width });
    const id = requestAnimationFrame(() => setReady(true));
    return () => cancelAnimationFrame(id);
  }, [value, items.length]);

  const trackStyle: CSSProperties = {
    position: "relative",
    display: "inline-flex",
    alignItems: "center",
    gap: sz.gap,
    height: sz.height,
    padding: 3,
    borderRadius: 999,
  };

  const pillStyle: CSSProperties = {
    position: "absolute",
    top: 3,
    left: 0,
    height: sz.height - 6,
    width: pill?.w ?? 0,
    transform: `translateX(${pill?.x ?? 0}px)`,
    borderRadius: 999,
    background: t.pill,
    boxShadow: t.pillShadow,
    transition: ready
      ? `transform 380ms ${EASE}, width 380ms ${EASE}`
      : "none",
    pointerEvents: "none",
    zIndex: 0,
    opacity: pill ? 1 : 0,
  };

  return (
    <GlassSurface
      ref={trackRef}
      role="tablist"
      variant={blur ? "frosted" : "static"}
      tone={tone}
      radius="pill"
      className="glass-toggle"
      style={trackStyle}
    >
      <span aria-hidden style={pillStyle} />
      {items.map((opt, i) => {
        const active = opt.value === value;
        const btnStyle: CSSProperties = {
          position: "relative",
          zIndex: 1,
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 6,
          height: sz.height - 6,
          padding: `0 ${sz.padX}px`,
          fontSize: sz.font,
          fontWeight: active ? 600 : 500,
          lineHeight: 1,
          color: active ? t.textActive : t.textIdle,
          background: "transparent",
          border: "none",
          borderRadius: 999,
          cursor: "pointer",
          appearance: "none",
          WebkitAppearance: "none",
          transition: "color 200ms ease",
          userSelect: "none",
        };
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
            style={btnStyle}
          >
            {opt.icon ? (
              <span style={{ display: "inline-flex" }}>{opt.icon}</span>
            ) : null}
            {opt.label}
          </button>
        );
      })}
    </GlassSurface>
  );
}

export default GlassToggle;
