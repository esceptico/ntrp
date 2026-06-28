import clsx from "clsx";

export interface MetaGridRow {
  label: string;
  value: string;
  mono?: boolean;
}

export function MetaGrid({ rows }: { rows: (MetaGridRow | null | false)[] }) {
  const present = rows.filter(Boolean) as MetaGridRow[];
  return (
    <dl className="grid grid-cols-[110px_minmax(0,1fr)] gap-y-2.5 text-sm">
      {present.map((row) => (
        <MetaRow key={row.label} row={row} />
      ))}
    </dl>
  );
}

function MetaRow({ row }: { row: MetaGridRow }) {
  return (
    <>
      <dt className="text-muted">{row.label}</dt>
      <dd
        className={clsx(
          "text-ink-soft min-w-0 tabular-nums",
          row.mono && "font-mono text-xs break-all whitespace-pre-wrap",
        )}
      >
        {row.value}
      </dd>
    </>
  );
}
