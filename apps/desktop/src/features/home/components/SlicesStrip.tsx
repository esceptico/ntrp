import { useRef } from "react";
import type { SliceSummary } from "@/api/slices";
import { useStore } from "@/stores";
import { TravelingHighlight } from "@/components/ui/TravelingHighlight";

/** Horizontal strip of every slice as a tonal chip: a live dot marks slices
 *  with active asks or a running agent; quiet slices sit at 55% opacity so
 *  the live ones read as "where attention currently is." TravelingHighlight
 *  rides hover via real DOM focus/pointer state against the row list. */
export function SlicesStrip({ slices }: { slices: SliceSummary[] }) {
  const openSlice = useStore((s) => s.openSlice);
  const listRef = useRef<HTMLDivElement | null>(null);

  if (slices.length === 0) return null;

  return (
    <div className="grid gap-2">
      <span className="text-2xs font-semibold tracking-wide text-faint uppercase">Slices</span>
      <div ref={listRef} className="relative flex flex-wrap gap-1.5">
        <TravelingHighlight listRef={listRef} watch="focus" className="rounded-full" />
        {slices.map((slice) => (
          <button
            key={slice.key}
            type="button"
            role="menuitem"
            onClick={() => openSlice(slice.key)}
            className="relative z-[1] inline-flex h-8 items-center gap-1.5 rounded-full bg-surface-soft px-3 text-[12.5px] font-medium text-ink"
            style={{ opacity: slice.live ? 1 : 0.55 }}
          >
            {slice.live && (
              <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-ink" />
            )}
            <span className="truncate">{slice.title}</span>
          </button>
        ))}
      </div>
      <p className="m-0 text-[11.5px] text-whisper">
        Quiet slices stay quiet — silence is the deliverable.
      </p>
    </div>
  );
}
