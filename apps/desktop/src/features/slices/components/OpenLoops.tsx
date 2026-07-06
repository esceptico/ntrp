import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { Collapse } from "@/components/ui/Collapse";

/** OPEN LOOPS rows: v1 loops are plain strings (no id/state), so each row
 *  is just a Collapse-driven in-place expand of its own full text — useful
 *  once loop strings get long enough to truncate. No per-row "agent
 *  completed" dimming yet since the shape carries no such flag; this is
 *  a hook point for whenever that lands server-side. */
export function OpenLoops({ loops }: { loops: string[] }) {
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  if (loops.length === 0) return null;

  return (
    <div className="grid gap-2">
      <span className="text-2xs font-semibold tracking-wide text-faint uppercase">Open loops</span>
      <div className="grid gap-px">
        {loops.map((loop, index) => {
          const open = openIndex === index;
          return (
            <div key={index} className="rounded-[10px] bg-surface-soft">
              <button
                type="button"
                onClick={() => setOpenIndex(open ? null : index)}
                className="flex w-full items-center gap-2 px-3.5 py-2.5 text-left text-sm text-ink-soft"
              >
                <ChevronRight
                  className="size-3.5 shrink-0 text-faint transition-transform duration-check"
                  style={{ transform: open ? "rotate(90deg)" : "rotate(0deg)" }}
                />
                <span className={open ? "min-w-0 flex-1" : "min-w-0 flex-1 truncate"}>{loop}</span>
              </button>
              <Collapse open={open}>
                <p className="px-3.5 pb-2.5 pl-[38px] text-sm text-ink-soft">{loop}</p>
              </Collapse>
            </div>
          );
        })}
      </div>
    </div>
  );
}
