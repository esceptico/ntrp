import { useStore, type UiMessage } from "@/stores";
import { messageInSourceFocus } from "@/lib/messageSourceFocus";

// Background tint only — the previous inset 1px ring stacked
// visually badly when several adjacent messages were focused at once,
// reading as overlapping outlines. The tint alone is enough cue.
export const SOURCE_FOCUS_CLASS = "scroll-mt-20 rounded-[10px] bg-accent-soft/35";

export function useMessage(id: string): UiMessage | undefined {
  return useStore((s) => s.messages.get(id));
}

export function useIsLast(id: string): boolean {
  return useStore((s) => s.order[s.order.length - 1] === id);
}

export function useSourceFocused(id: string): boolean {
  return useStore((s) => messageInSourceFocus(s.messages.get(id), s.sourceFocus, s.currentSessionId));
}

export function entryAnimation(message: UiMessage, className: string): string | undefined {
  return message.suppressEntryMotion ? undefined : className;
}
