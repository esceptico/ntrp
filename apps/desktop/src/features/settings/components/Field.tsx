import { useState } from "react";
import { Input } from "@/components/ui/Input";
import { Slider } from "@/components/ui/Slider";

const clamp = (n: number, min: number, max: number) => Math.max(min, Math.min(max, n));

/** Editable numeric value: type a precise number (committed on blur / Enter,
 *  clamped to [min,max]) or step it with Arrow keys. The native spinner is
 *  hidden. Pairs with a Slider for coarse drag — the Slider alone isn't enough
 *  to set an exact value. */
function NumberInput({
  id,
  value,
  onChange,
  min,
  max,
  step,
  suffix,
  ariaLabel,
}: {
  id?: string;
  value: number;
  onChange: (n: number) => void;
  min: number;
  max: number;
  step: number;
  suffix?: string;
  ariaLabel?: string;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const commit = () => {
    if (draft === null) return;
    const n = Number(draft);
    if (Number.isFinite(n) && draft.trim() !== "") onChange(clamp(n, min, max));
    setDraft(null);
  };
  return (
    <div className="flex items-center gap-1.5">
      <input
        id={id}
        type="number"
        inputMode="numeric"
        aria-label={ariaLabel}
        value={draft ?? String(value)}
        min={min}
        max={max}
        step={step}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") e.currentTarget.blur();
        }}
        className="w-[64px] h-7 rounded-md border border-line bg-transparent px-2 text-sm tabular-nums text-right text-ink outline-none transition-[border-color,box-shadow] hover:border-line-strong focus:border-accent focus:shadow-[0_0_0_3px_var(--color-accent-soft)] [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
      />
      <span className="w-14 text-xs text-faint">{suffix}</span>
    </div>
  );
}

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
        <label htmlFor={id} className="text-sm font-medium tracking-[-0.005em] text-ink-soft">{label}</label>
        {help && <span className="text-xs text-faint leading-[1.4]">{help}</span>}
      </div>
      <div className="flex items-center gap-3 justify-self-end">
        <Slider className="w-44" aria-label={label} value={value} min={min} max={max} step={step} onChange={onChange} />
        <NumberInput id={id} value={value} onChange={onChange} min={min} max={max} step={step} suffix={suffix} ariaLabel={label} />
      </div>
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
  step = 1,
}: {
  label: string;
  value: number;
  onChange: (next: number) => void;
  help?: string;
  min?: number;
  max?: number;
  step?: number;
}) {
  const percent = Math.round(value * 100);
  const id = `pctfield-${label.replace(/\s+/g, "-").toLowerCase()}`;
  const setPercent = (n: number) => onChange(n / 100);
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1">
      <div className="grid gap-0.5">
        <label htmlFor={id} className="text-sm font-medium tracking-[-0.005em] text-ink-soft">{label}</label>
        {help && <span className="text-xs text-faint leading-[1.4]">{help}</span>}
      </div>
      <div className="flex items-center gap-3 justify-self-end">
        <Slider className="w-44" aria-label={label} value={percent} min={min} max={max} step={step} onChange={setPercent} />
        <NumberInput id={id} value={percent} onChange={setPercent} min={min} max={max} step={step} suffix="%" ariaLabel={label} />
      </div>
    </div>
  );
}
