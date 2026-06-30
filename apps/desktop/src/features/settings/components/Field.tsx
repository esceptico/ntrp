import type { ReactNode } from "react";
import { Input } from "@/components/ui/Input";
import { Slider } from "@/components/ui/Slider";

/** Labelled text/password input for settings forms. Thin convenience wrapper
 *  over {@link Input} with the settings defaults (no spellcheck/autocomplete)
 *  and a string-valued onChange. */
export function Field({
  label,
  value,
  onChange,
  placeholder,
  help,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  help?: string;
  type?: "text" | "password";
}) {
  const helpId = help ? `field-${label.replace(/\s+/g, "-").toLowerCase()}-help` : undefined;
  return (
    <div className="grid gap-1.5">
      <Input
        label={label}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        spellCheck={false}
        autoComplete="off"
        aria-describedby={helpId}
      />
      {help && (
        <span id={helpId} className="text-xs leading-[1.4] text-faint">
          {help}
        </span>
      )}
    </div>
  );
}

export function NumberField({
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
  help,
  suffix,
}: {
  label: string;
  value: number;
  onChange: (next: number) => void;
  min: number;
  max: number;
  step?: number;
  help?: string;
  suffix?: string;
}) {
  const id = `numfield-${label.replace(/\s+/g, "-").toLowerCase()}`;
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1">
      <div className="grid gap-0.5">
        <span id={id} className="text-sm font-medium tracking-[-0.005em] text-ink-soft">{label}</span>
        {help && <span className="text-xs text-faint leading-[1.4]">{help}</span>}
      </div>
      <Slider
        className="w-52"
        aria-labelledby={id}
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={onChange}
        formatValue={(n) => (suffix ? `${n} ${suffix}` : `${n}`)}
      />
    </div>
  );
}

/** Edits a 0..1 fraction as an integer percent (0..100). Saves the fraction. */
export function PercentField({
  label,
  value,
  onChange,
  help,
  min = 0,
  max = 100,
}: {
  label: string;
  value: number;
  onChange: (next: number) => void;
  help?: string;
  min?: number;
  max?: number;
}) {
  const percent = Math.round(value * 100);
  const id = `pctfield-${label.replace(/\s+/g, "-").toLowerCase()}`;
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1">
      <div className="grid gap-0.5">
        <span id={id} className="text-sm font-medium tracking-[-0.005em] text-ink-soft">{label}</span>
        {help && <span className="text-xs text-faint leading-[1.4]">{help}</span>}
      </div>
      <Slider
        className="w-52"
        aria-labelledby={id}
        value={percent}
        min={min}
        max={max}
        step={1}
        onChange={(n) => onChange(n / 100)}
        formatValue={(n) => `${n}%`}
      />
    </div>
  );
}

/** Wraps a caller-provided control with a label. Use when the control
 *  isn't a plain text input (a select, a toggle group, a custom editor). */
export function LabeledField({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div role="group" aria-label={label} className="grid gap-1.5">
      <span className="text-sm font-medium tracking-[-0.005em] text-ink-soft">{label}</span>
      {children}
    </div>
  );
}
