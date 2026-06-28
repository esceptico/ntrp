import type { MemoryArtifact } from "@/api/memoryArtifacts";

export function TimelineDisclosure({ timeline }: { timeline?: MemoryArtifact["timeline"] }) {
  const records = (timeline ?? []).filter((l) => !l.superseded);
  const supersededCount = (timeline ?? []).length - records.length;
  if (records.length === 0) return null;
  const label = records.length === 1 ? "record" : "records";
  return (
    <details className="mt-6 border-t border-line pt-3">
      <summary className="cursor-pointer text-xs font-medium text-muted">Timeline · {records.length} {label}</summary>
      <ol className="mt-2 space-y-1">
        {records.map((l) => (
          <li key={l.id} className="flex gap-2 text-xs">
            <span className="shrink-0 font-mono tabular-nums text-muted">{l.date}</span>
            <span className="min-w-0 break-words text-ink">{l.text}</span>
            <span className="ml-auto shrink-0 text-muted">{l.src}</span>
          </li>
        ))}
      </ol>
      {supersededCount > 0 && <div className="mt-2 text-xs text-muted">+{supersededCount} superseded</div>}
    </details>
  );
}
