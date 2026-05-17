interface RangeFieldProps {
  label: string;
  value: number;
  onChange: (next: number) => void;
  min: number;
  max: number;
  step?: number;
  /** Suffix shown after the value (e.g. "px", "%"). */
  unit?: string;
  help?: string;
}

export function RangeField({
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
  unit,
  help,
}: RangeFieldProps) {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1">
      <div className="grid gap-0.5">
        <label className="text-sm font-medium text-ink">{label}</label>
        {help && <span className="text-xs text-faint leading-[1.4]">{help}</span>}
      </div>
      <div className="flex items-center gap-2 w-[200px]">
        <input
          type="range"
          value={value}
          min={min}
          max={max}
          step={step}
          onChange={(e) => onChange(Number(e.target.value))}
          className="flex-1 accent-accent cursor-pointer"
        />
        <span className="w-12 text-right text-sm text-ink-soft tabular-nums font-mono">
          {Math.round(value)}{unit ?? ""}
        </span>
      </div>
    </div>
  );
}
