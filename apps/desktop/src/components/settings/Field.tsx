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
  return (
    <div className="grid gap-1">
      <label className="text-xs font-medium uppercase tracking-[0.06em] text-muted">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        spellCheck={false}
        autoComplete="off"
        className="w-full h-9 px-3 border border-line rounded-[9px] bg-surface text-ink text-base outline-none hover:border-line-strong focus:border-accent focus:shadow-[0_0_0_3px_var(--color-accent-soft)] transition-[border-color,box-shadow]"
      />
      {help && <span className="text-xs text-faint leading-[1.4]">{help}</span>}
    </div>
  );
}

export function NumberField({
  label,
  value,
  onChange,
  min,
  max,
  help,
  suffix,
}: {
  label: string;
  value: number;
  onChange: (next: number) => void;
  min: number;
  max: number;
  help?: string;
  suffix?: string;
}) {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1">
      <div className="grid gap-0.5">
        <div className="flex items-baseline gap-1.5">
          <label className="text-sm font-medium text-ink">{label}</label>
          {suffix && <span className="text-xs text-faint">{suffix}</span>}
        </div>
        {help && <span className="text-xs text-faint leading-[1.4]">{help}</span>}
      </div>
      <div className="flex items-center gap-2">
        <input
          type="number"
          value={value}
          min={min}
          max={max}
          step="any"
          onChange={(e) => {
            const n = Number(e.target.value);
            if (Number.isFinite(n)) onChange(n);
          }}
          className="w-[88px] h-8 px-2 border border-line rounded-md bg-surface text-ink text-sm tabular-nums outline-none hover:border-line-strong focus:border-accent focus:shadow-[0_0_0_3px_var(--color-accent-soft)] transition-[border-color,box-shadow]"
        />
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
}: {
  label: string;
  value: number;
  onChange: (next: number) => void;
  help?: string;
  min?: number;
  max?: number;
}) {
  const percent = Math.round(value * 100);
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1">
      <div className="grid gap-0.5">
        <label className="text-sm font-medium text-ink">{label}</label>
        {help && <span className="text-xs text-faint leading-[1.4]">{help}</span>}
      </div>
      <div className="relative">
        <input
          type="number"
          value={percent}
          min={min}
          max={max}
          step="any"
          onChange={(e) => {
            const n = Number(e.target.value);
            if (!Number.isFinite(n)) return;
            const clamped = Math.max(min, Math.min(max, n));
            onChange(clamped / 100);
          }}
          className="w-[88px] h-8 pl-2 pr-6 border border-line rounded-md bg-surface text-ink text-sm tabular-nums outline-none hover:border-line-strong focus:border-accent focus:shadow-[0_0_0_3px_var(--color-accent-soft)] transition-[border-color,box-shadow]"
        />
        <span className="pointer-events-none absolute inset-y-0 right-2 grid place-items-center text-xs text-faint">
          %
        </span>
      </div>
    </div>
  );
}
