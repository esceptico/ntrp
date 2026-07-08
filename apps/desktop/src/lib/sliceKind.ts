import type { SliceAsk } from "@/api/slices";

/** One vocabulary for an ask's kind, shared by Home's FocusRow and the
 *  room's AskCard so an ask presents its kind identically in both places.
 *  `label` is the monochrome-safe signal (the dot collapses to a neutral
 *  grey in the default theme); `dot` is the severity cue that lights up in
 *  an accent theme — attention kinds (act/drift) warmer. */
export const ASK_KIND: Record<SliceAsk["kind"], { dot: string; label: string }> = {
  review: { dot: "bg-muted", label: "review" },
  decide: { dot: "bg-accent", label: "decide" },
  act: { dot: "bg-warn", label: "act" },
  drift: { dot: "bg-bad", label: "drift" },
};
