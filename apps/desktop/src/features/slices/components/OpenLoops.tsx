import { useState } from "react";

/** OPEN LOOPS rows: v1 loops are plain strings (no id/state), so a row is
 *  collapsed to one truncated line and expands IN PLACE to its full wrapped
 *  text — one copy of the text, toggled between truncate and wrap. Every
 *  wrapper down the chain needs min-w-0: these are grid/flex items whose
 *  min-content size is the untruncated line, and without it long loops blow
 *  the track past the 640px column (bit us with real vault data). No
 *  per-row "agent completed" dimming yet — the shape carries no such flag;
 *  hook point for whenever that lands server-side. */
export function OpenLoops({ loops }: { loops: string[] }) {
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  if (loops.length === 0) return null;

  return (
    <div className="grid min-w-0 gap-2">
      <span className="text-2xs font-semibold tracking-wide text-faint uppercase">Open loops</span>
      {/* Quiet hairline list (mock: separators, no tonal bars) — tone is
          reserved for things that need attention; loops are ambient. */}
      <div className="grid min-w-0">
        {loops.map((loop, index) => {
          const open = openIndex === index;
          return (
            <button
              key={index}
              type="button"
              onClick={() => setOpenIndex(open ? null : index)}
              className={`group flex min-w-0 items-start gap-2.5 py-2.5 text-left text-sm text-ink-soft ${
                index > 0 ? "border-t border-line-soft" : ""
              }`}
            >
              {/* Mock marker: a quiet dot, not a chevron — expandability
                  reads through the hover tint + wrap behavior. */}
              <span
                aria-hidden
                className="mt-[7px] size-1.5 shrink-0 rounded-full bg-muted transition-colors group-hover:bg-ink-soft"
              />
              <span className={open ? "min-w-0 flex-1 whitespace-normal" : "min-w-0 flex-1 truncate"}>
                {loop}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
