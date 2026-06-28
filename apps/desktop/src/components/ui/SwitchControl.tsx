import { CSSProperties, Ref } from "react";

interface SwitchControlProps {
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

export function SwitchControl({
  checked,
  onChange,
  size = "md",
  disabled = false,
  className,
  "aria-label": ariaLabel,
  ref,
}: SwitchControlProps) {
  const sz = SIZES[size];
  const tx = checked ? sz.onMax : sz.offMin;

  const trackStyle: CSSProperties = {
    "--gs-track-w": `${sz.w}px`,
    "--gs-track-h": `${sz.h}px`,
    "--gs-knob-size": `${sz.knob}px`,
    "--gs-knob-top": `${(sz.h - 2 - sz.knob) / 2}px`,
  } as CSSProperties;

  const knobStyle: CSSProperties = {
    transform: `translateX(${tx}px)`,
  };

  const classes = [
    "switch-control",
    checked ? "switch-control-on" : null,
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
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={classes}
      style={trackStyle}
    >
      <span aria-hidden className="switch-control-knob" style={knobStyle} />
    </button>
  );
}

export default SwitchControl;
