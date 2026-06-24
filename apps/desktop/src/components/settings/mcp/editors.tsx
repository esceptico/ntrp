import clsx from "clsx";
import { AddBtn, RemoveBtn } from "./atoms";

export interface KeyVal {
  key: string;
  value: string;
}

export function kvToRecord(entries: KeyVal[]): Record<string, string> | null {
  const out: Record<string, string> = {};
  for (const e of entries) {
    const k = e.key.trim();
    if (!k) continue;
    out[k] = e.value;
  }
  return Object.keys(out).length === 0 ? null : out;
}

export function ListEditor({
  values,
  onChange,
  placeholder,
  addLabel,
  mono,
}: {
  values: string[];
  onChange: (v: string[]) => void;
  placeholder: string;
  addLabel: string;
  mono?: boolean;
}) {
  const update = (i: number, v: string) => {
    const next = values.slice();
    next[i] = v;
    onChange(next);
  };
  const remove = (i: number) => {
    const next = values.filter((_, idx) => idx !== i);
    onChange(next.length === 0 ? [""] : next);
  };
  return (
    <div className="grid gap-1.5">
      {values.map((v, i) => (
        <div key={i} className="flex items-center gap-1.5">
          <input
            type="text"
            value={v}
            onChange={(e) => update(i, e.target.value)}
            placeholder={placeholder}
            aria-label={`${placeholder} ${i + 1}`}
            spellCheck={false}
            className={clsx(
              "flex-1 input-field input-field-sm",
              mono && "font-mono",
            )}
          />
          <RemoveBtn onClick={() => remove(i)} />
        </div>
      ))}
      <AddBtn label={addLabel} onClick={() => onChange([...values, ""])} />
    </div>
  );
}

export function KeyValueEditor({
  entries,
  onChange,
  addLabel,
  valuePlaceholder = "Value",
}: {
  entries: KeyVal[];
  onChange: (v: KeyVal[]) => void;
  addLabel: string;
  valuePlaceholder?: string;
}) {
  const update = (i: number, patch: Partial<KeyVal>) => {
    const next = entries.slice();
    next[i] = { ...next[i], ...patch };
    onChange(next);
  };
  const remove = (i: number) => {
    const next = entries.filter((_, idx) => idx !== i);
    onChange(next.length === 0 ? [{ key: "", value: "" }] : next);
  };
  return (
    <div className="grid gap-1.5">
      {entries.map((e, i) => (
        <div key={i} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] gap-1.5">
          <input
            type="text"
            value={e.key}
            onChange={(ev) => update(i, { key: ev.target.value })}
            placeholder="Key"
            aria-label={`Key ${i + 1}`}
            spellCheck={false}
            className="input-field input-field-sm font-mono"
          />
          <input
            type="text"
            value={e.value}
            onChange={(ev) => update(i, { value: ev.target.value })}
            placeholder={valuePlaceholder}
            aria-label={`${valuePlaceholder} ${i + 1}`}
            spellCheck={false}
            className="input-field input-field-sm font-mono"
          />
          <RemoveBtn onClick={() => remove(i)} />
        </div>
      ))}
      <AddBtn label={addLabel} onClick={() => onChange([...entries, { key: "", value: "" }])} />
    </div>
  );
}
