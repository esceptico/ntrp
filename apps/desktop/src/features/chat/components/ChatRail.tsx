import { useEffect, useRef, useState } from "react";
import clsx from "clsx";
import { useShallow } from "zustand/react/shallow";
import { useStore } from "@/stores";

// Codex-style conversation minimap: one line-tick per turn, anchored to the
// left edge of the chat. The tick expands on hover/active (inspired by
// @ncdai/line-nav), scroll-spy lights the turn you're reading, and hover
// reveals the prompt as a tooltip. Click jumps to the turn.
export function ChatRail({
  turnIds,
  scrollRef,
}: {
  turnIds: string[];
  scrollRef: { current: HTMLElement | null };
}) {
  const titles = useStore(
    useShallow((s) => turnIds.map((id) => (s.messages.get(id)?.content ?? "").trim())),
  );
  const [activeId, setActiveId] = useState<string | null>(null);

  useEffect(() => {
    const root = scrollRef.current;
    if (!root || turnIds.length === 0) return;
    let raf = 0;
    const update = () => {
      raf = 0;
      // At the bottom the tail turns can't push their top past the read line,
      // so snap to the last turn — otherwise it sticks on an earlier one.
      if (root.scrollHeight - root.clientHeight - root.scrollTop < 8) {
        setActiveId(turnIds[turnIds.length - 1]);
        return;
      }
      // Read line sits just below the header fade — the turn whose top last
      // crossed it is the one being read.
      const readLine = root.getBoundingClientRect().top + 96;
      let active: string | null = null;
      for (const el of root.querySelectorAll<HTMLElement>("[data-turn-id]")) {
        if (el.getBoundingClientRect().top <= readLine) active = el.dataset.turnId ?? active;
        else break;
      }
      setActiveId(active ?? turnIds[0]);
    };
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(update);
    };
    update();
    root.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      root.removeEventListener("scroll", onScroll);
      if (raf) cancelAnimationFrame(raf);
    };
  }, [scrollRef, turnIds]);

  const activeRef = useRef<HTMLButtonElement | null>(null);

  // Follow the active tick when a long history scrolls the rail.
  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "nearest" });
  }, [activeId]);

  // ponytail: a one-turn chat doesn't need a minimap.
  if (turnIds.length < 2) return null;

  const scrollTo = (id: string) => {
    scrollRef.current
      ?.querySelector<HTMLElement>(`[data-turn-id="${CSS.escape(id)}"]`)
      ?.scrollIntoView({ block: "start", behavior: "smooth" });
  };

  return (
    // Centred band with fixed-size ticks. When the history is longer than the
    // band, the rail scrolls internally (active tick auto-followed) rather than
    // squishing the ticks. The container is wide enough that the hover tooltip
    // fits inside it — overflow-y:auto would otherwise clip it on the x-axis.
    // pointer-events only on the ticks, so the wide overlay never blocks chat.
    <nav
      aria-label="Conversation"
      className="absolute inset-y-[16%] left-0 z-[6] hidden @[820px]:flex w-[320px] flex-col overflow-y-auto overflow-x-hidden pl-2 pointer-events-none [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
    >
      <div className="my-auto flex shrink-0 flex-col items-start gap-[6px] py-1">
        {turnIds.map((id, i) => {
          const active = id === activeId;
          return (
            <button
              key={id}
              ref={active ? activeRef : undefined}
              type="button"
              onClick={() => scrollTo(id)}
              aria-current={active ? "true" : undefined}
              aria-label={titles[i] || "Message"}
              className="group pointer-events-auto relative flex h-[9px] items-center after:absolute after:content-[''] after:-inset-y-[7px] after:-left-2 after:-right-8"
            >
              <span
                className={clsx(
                  "block h-[2px] rounded-full transition-[width,background-color] duration-200 ease-out",
                  active ? "w-4 bg-ink" : "w-2.5 bg-ink/25 group-hover:w-4 group-hover:bg-ink",
                )}
              />
              <span className="pointer-events-none absolute left-full ml-2 z-10 max-w-[280px] truncate rounded-md bg-ink px-2 py-1 text-xs text-on-ink opacity-0 shadow-md transition-opacity duration-150 group-hover:opacity-100">
                {titles[i] || "Message"}
              </span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
