import { useMemo, useRef, useState } from "react";
import { useStore } from "@/stores";
import { sendMessage } from "@/actions/messages";
import { runAutomation } from "@/actions/automations";
import { switchSession } from "@/actions/sessions";
import { routeHeroInput, type HeroSuggestion } from "@/features/home/lib/heroRouting";
import { TravelingHighlight } from "@/components/ui/TravelingHighlight";

// Stable references for "not loaded yet" fallbacks — a selector that falls
// back to `?? []` inline returns a NEW array every render, which zustand
// treats as a changed value and forces an infinite re-render loop.
const NO_SLICES: { key: string; title: string }[] = [];
const NO_AUTOMATIONS: { task_id: string; name: string }[] = [];

const KIND_LABEL: Record<HeroSuggestion["kind"], string> = {
  chat: "Chat",
  slice: "Slice",
  session: "Session",
  automation: "Automation",
  skill: "Skill",
};

/** The hero input IS the composer promoted: same draft/setDraft/sendMessage
 *  machinery as the in-thread Composer, just no picker/toolbar/images chrome.
 *  Typing routes through heroRouting for a small suggestion list; Enter with
 *  no explicit selection always sends as a chat message — the door never
 *  blocks typing. */
export function HeroInput() {
  const draft = useStore((s) => s.draft);
  const setDraft = useStore((s) => s.setDraft);
  const openSlice = useStore((s) => s.openSlice);
  const sessions = useStore((s) => s.sessions);
  const slices = useStore((s) => s.slices.overview?.slices ?? NO_SLICES);
  const automations = useStore((s) => s.automations ?? NO_AUTOMATIONS);
  const skills = useStore((s) => s.skills);

  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  const suggestions = useMemo(
    () => routeHeroInput(draft, { sessions, slices, automations, skills }),
    [draft, sessions, slices, automations, skills],
  );
  const showSuggestions = draft.trim().length > 0 && suggestions.length > 1;

  const applySuggestion = (suggestion: HeroSuggestion) => {
    switch (suggestion.kind) {
      case "chat":
        void sendMessage(suggestion.label);
        setDraft("");
        break;
      case "slice":
        openSlice(suggestion.ref);
        setDraft("");
        break;
      case "session":
        void switchSession(suggestion.ref);
        setDraft("");
        break;
      case "automation":
        void runAutomation(suggestion.ref);
        setDraft("");
        break;
      case "skill":
        setDraft(`/${suggestion.ref} `);
        break;
    }
    setActiveIndex(null);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" && showSuggestions) {
      e.preventDefault();
      setActiveIndex((i) => (i === null ? 0 : Math.min(i + 1, suggestions.length - 1)));
      return;
    }
    if (e.key === "ArrowUp" && showSuggestions) {
      e.preventDefault();
      setActiveIndex((i) => (i === null ? 0 : Math.max(i - 1, 0)));
      return;
    }
    if (e.key === "Escape") {
      setActiveIndex(null);
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      const chosen = activeIndex !== null ? suggestions[activeIndex] : suggestions[0];
      if (chosen) applySuggestion(chosen);
    }
  };

  return (
    <div className="relative">
      <div className="flex h-14 items-center gap-2 rounded-[14px] border border-line bg-surface px-4">
        <input
          id="message-input"
          type="text"
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value);
            setActiveIndex(null);
          }}
          onKeyDown={onKeyDown}
          placeholder="Ask, search, or start a chat…"
          autoFocus
          className="min-w-0 flex-1 bg-transparent text-[15px] text-ink placeholder:text-faint focus:outline-none"
        />
        <kbd className="shrink-0 rounded-md bg-surface-soft px-1.5 py-0.5 text-2xs font-medium text-faint">
          ⌘K
        </kbd>
      </div>
      {showSuggestions && (
        <div
          ref={listRef}
          className="surface-panel surface-radius-md absolute inset-x-0 top-[calc(100%+8px)] z-10 grid gap-0.5 p-1"
        >
          <TravelingHighlight listRef={listRef} watch="selected" className="rounded-[8px]" />
          {suggestions.map((suggestion, index) => (
            <button
              key={`${suggestion.kind}-${suggestion.ref}-${index}`}
              type="button"
              data-selected={activeIndex === index ? "true" : undefined}
              onMouseEnter={() => setActiveIndex(index)}
              onClick={() => applySuggestion(suggestion)}
              className="relative z-[1] flex items-center gap-2 rounded-[8px] px-2.5 py-1.5 text-left text-sm text-ink"
            >
              <span className="w-20 shrink-0 text-xs text-faint">{KIND_LABEL[suggestion.kind]}</span>
              <span className="min-w-0 flex-1 truncate">{suggestion.label || "Send message"}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
