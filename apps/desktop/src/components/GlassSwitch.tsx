import { CSSProperties, Ref } from "react";

interface GlassSwitchProps {
  checked: boolean;
  onChange: (next: boolean) => void;
  size?: "sm" | "md";
  disabled?: boolean;
  className?: string;
  "aria-label"?: string;
  ref?: Ref<HTMLButtonElement>;
}

const SIZES = {
  sm: { w: 30, h: 18, knob: 14, offMin: 2, onMax: 14 },
  md: { w: 36, h: 22, knob: 18, offMin: 2, onMax: 16 },
} as const;

export function GlassSwitch({
  checked,
  onChange,
  size = "md",
  disabled = false,
  className,
  "aria-label": ariaLabel,
  ref,
}: GlassSwitchProps) {
  const sz = SIZES[size];
  const tx = checked ? sz.onMax : sz.offMin;

  const trackStyle: CSSProperties = {
    position: "relative",
    display: "inline-flex",
    alignItems: "center",
    width: sz.w,
    height: sz.h,
    flexShrink: 0,
    padding: 0,
    border: "1px solid var(--gs-track-border)",
    borderRadius: 999,
    background: "var(--gs-track-bg)",
    boxShadow: "var(--gs-track-shadow)",
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.5 : 1,
    appearance: "none",
    WebkitAppearance: "none",
    transition: "background 220ms ease, border-color 220ms ease, box-shadow 220ms ease",
  };

  const knobStyle: CSSProperties = {
    position: "absolute",
    top: (sz.h - 2 - sz.knob) / 2,
    left: 0,
    width: sz.knob,
    height: sz.knob,
    borderRadius: 999,
    background: "var(--gs-knob-bg)",
    border: "1px solid var(--gs-knob-border)",
    boxShadow: "var(--gs-knob-shadow)",
    transform: `translateX(${tx}px)`,
    transition: "transform 220ms cubic-bezier(0.32, 0.72, 0, 1)",
    pointerEvents: "none",
  };

  const classes = [
    "glass-switch",
    checked ? "glass-switch-on" : null,
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button
      ref={ref}
      type="button"
      role="switch"
      aria-checked={checked}
      aria-disabled={disabled || undefined}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={() => {
        if (disabled) return;
        onChange(!checked);
      }}
      className={classes}
      style={trackStyle}
    >
      <span aria-hidden className="glass-switch-knob" style={knobStyle} />
    </button>
  );
}

export default GlassSwitch;
