import { useEffect, useMemo, useRef, useState } from "react";
import { useShallow } from "zustand/react/shallow";
import { ScrollFadeBottom, ScrollFadeTop } from "@/components/ui/ScrollBlur";
import { useStore } from "@/stores";

// Codex-style conversation minimap: one line-tick per turn, anchored to the
// left edge of the chat. Scroll-spy inks the turn you're reading; click jumps.
// Hover is a proximity FIELD (per design-language: selection travels, hover is
// proximity): tick widths follow a gaussian falloff around the cursor —
// per-frame writes with the transition disabled while live, so the tween never
// fights the pointer — and ONE label travels between ticks showing the prompt,
// blur-ramping in and out instead of per-tick tooltip flips.

const BASE_W = 12;
const ACTIVE_W = 18;
const HOVER_W = 32;
const SIGMA_Y = 12;
// The tick's own extent (mark + its hit area) counts as distance zero —
// hovering ON the rail is always full strength; the falloff starts beyond it.
const FULL_X = 32;
// Liquid: the field is 2D — amplitude also follows the cursor's horizontal
// approach, so the ticks swell BEFORE the pointer reaches the rail. The nav
// overlay is pointer-events-none, so the sensor is a document-level
// pointermove gated to the band's neighborhood.
const SIGMA_X = 24;
const MAX_DX = 64;
const MAX_DY = 48;
const FADE_X = 20; // envelope: field smoothsteps to 0 over this span at the edges
// Label commits only near full strength; hysteresis so it can't flicker.
const LABEL_ON = 0.5;
const LABEL_OFF = 0.38;

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
  // Turns currently on screen, as a joined key — string state so identical
  // frames bail out of re-rendering for free.
  const [visibleKey, setVisibleKey] = useState("");

  useEffect(() => {
    const root = scrollRef.current;
    if (!root || turnIds.length === 0) return;
    let raf = 0;
    const update = () => {
      raf = 0;
      const rootRect = root.getBoundingClientRect();
      // Read line sits just below the header fade — the turn whose top last
      // crossed it is the one being read.
      const readLine = rootRect.top + 96;
      let active: string | null = null;
      const vis: string[] = [];
      for (const el of root.querySelectorAll<HTMLElement>("[data-turn-id]")) {
        const id = el.dataset.turnId;
        if (!id) continue;
        const r = el.getBoundingClientRect();
        if (r.top <= readLine) active = id;
        if (r.bottom > rootRect.top && r.top < rootRect.bottom) vis.push(id);
      }
      // At the bottom the tail turns can't push their top past the read line,
      // so snap to the last turn — otherwise it sticks on an earlier one.
      if (root.scrollHeight - root.clientHeight - root.scrollTop < 8) {
        active = turnIds[turnIds.length - 1];
      }
      setActiveId(active ?? turnIds[0]);
      setVisibleKey(vis.join("\n"));
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

  const visibleSet = useMemo(() => new Set(visibleKey.split("\n")), [visibleKey]);

  // Turns present at mount render statically; turns that arrive later grow
  // in (height + blur ramp) instead of popping the band taller.
  const initialIds = useRef<Set<string> | null>(null);
  if (initialIds.current === null) initialIds.current = new Set(turnIds);

  const activeRef = useRef<HTMLButtonElement | null>(null);

  // Follow the active tick when a long history scrolls the rail — instantly,
  // so the rail tracks chat scrolling without lag. A just-arrived tick is
  // still growing its slot, so a deferred second pass re-aims once the
  // entrance animation settles. The ticks' scroll-margin gives the follow a
  // scrolloff buffer: the active tick lands clear of the edge fades with
  // neighbors visible, never dimmed at the very border.
  useEffect(() => {
    const follow = () => activeRef.current?.scrollIntoView({ block: "nearest" });
    follow();
    const t = setTimeout(follow, 250);
    return () => clearTimeout(t);
  }, [activeId]);

  const bandRef = useRef<HTMLDivElement | null>(null);
  const labelRef = useRef<HTMLDivElement | null>(null);
  const ticksRef = useRef<(HTMLSpanElement | null)[]>([]);
  const activeIndexRef = useRef(-1);
  activeIndexRef.current = turnIds.indexOf(activeId ?? "");
  const titlesRef = useRef(titles);
  titlesRef.current = titles;

  useEffect(() => {
    const band = bandRef.current, label = labelRef.current;
    if (!band || !label) return;
    let raf = 0;

    let engaged = false;
    let labelOn = false;

    const baseOf = (i: number) => (i === activeIndexRef.current ? ACTIVE_W : BASE_W);

    const rest = () => {
      engaged = false;
      labelOn = false;
      ticksRef.current.forEach((tick, i) => {
        if (!tick) return;
        tick.style.transition =
          "width var(--duration-panel) var(--ease-hover), background-color var(--duration-panel) var(--ease-hover)";
        tick.style.width = `${baseOf(i)}px`;
      });
      label.style.transition =
        "opacity var(--duration-fast) var(--ease-hover), filter var(--duration-fast) var(--ease-hover)";
      label.style.opacity = "0";
      label.style.filter = "blur(2px)";
    };

    // 2D gaussian: vertical falloff shapes the bell, horizontal distance to
    // each tick's anchor scales its amplitude. `env` is the boundary
    // envelope — it takes the whole field to exactly 0 at the engagement
    // edges, so crossing them never steps. Returns the nearest tick and the
    // field strength there.
    const field = (cursorX: number, cursorY: number, env: number) => {
      let nearest = 0, nearestD = Infinity, strength = 0;
      ticksRef.current.forEach((tick, i) => {
        if (!tick) return;
        const r = tick.getBoundingClientRect();
        const dy = cursorY - (r.top + r.height / 2);
        const dx = Math.max(0, cursorX - (r.left + FULL_X));
        const g =
          env * Math.exp(-(dy * dy) / (2 * SIGMA_Y * SIGMA_Y) - (dx * dx) / (2 * SIGMA_X * SIGMA_X));
        const base = baseOf(i);
        tick.style.transition = "none";
        tick.style.width = `${base + (HOVER_W - base) * g}px`;
        if (Math.abs(dy) < nearestD) {
          nearestD = Math.abs(dy);
          nearest = i;
          strength = g;
        }
      });
      return { nearest, strength };
    };

    const moveLabel = (index: number, strength: number) => {
      labelOn = labelOn ? strength > LABEL_OFF : strength > LABEL_ON;
      if (!labelOn) {
        label.style.transition =
          "opacity var(--duration-fast) var(--ease-hover), filter var(--duration-fast) var(--ease-hover)";
        label.style.opacity = "0";
        label.style.filter = "blur(2px)";
        return;
      }
      const tick = ticksRef.current[index];
      if (!tick) return;
      const tr = tick.getBoundingClientRect();
      const br = band.getBoundingClientRect();
      const visible = label.style.opacity === "1";
      label.style.transition = visible
        ? "top var(--duration-panel) var(--ease-hover), opacity var(--duration-fast) var(--ease-hover), filter var(--duration-fast) var(--ease-hover)"
        : "opacity var(--duration-fast) var(--ease-hover), filter var(--duration-fast) var(--ease-hover)";
      label.style.top = `${tr.top + tr.height / 2 - br.top}px`;
      label.textContent = titlesRef.current[index] || "Message";
      label.style.opacity = "1";
      label.style.filter = "blur(0)";
    };

    const onMove = (e: PointerEvent) => {
      const { clientX: x, clientY: y } = e;
      if (raf) cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        raf = 0;
        const br = band.getBoundingClientRect();
        // The liquid lives in the GUTTER: engagement stops at the chat
        // content's left edge, so the field never stirs while the user is
        // reading or interacting with the chat itself. MAX_DX stays as the
        // outer bound (at that distance the field is ~0 anyway). The column
        // is re-queried per run — session switches replace the node, and a
        // captured reference would go stale.
        const contentLeft =
          scrollRef.current
            ?.querySelector<HTMLElement>(".messages-inner")
            ?.getBoundingClientRect().left ?? Infinity;
        const limit = Math.min(br.left + MAX_DX, contentLeft);
        if (y < br.top - MAX_DY || y > br.bottom + MAX_DY) {
          if (engaged) rest();
          return;
        }
        // Boundary envelope: smoothstep to 0 over the last FADE_X px before
        // each horizontal edge (left = sidebar side, right = content side),
        // so engagement never steps from rest to a visible value.
        const t = Math.min((limit - x) / FADE_X, (x - (br.left - 16)) / FADE_X, 1);
        if (t <= 0) {
          if (engaged) rest();
          return;
        }
        engaged = true;
        const env = t * t * (3 - 2 * t);
        const { nearest, strength } = field(x, y, env);
        moveLabel(nearest, strength);
      });
    };

    document.addEventListener("pointermove", onMove, { passive: true });
    return () => {
      document.removeEventListener("pointermove", onMove);
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);

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
    // squishing the ticks. The container is wide enough that the traveling
    // label fits inside it — overflow-y:auto would otherwise clip it on the
    // x-axis. pointer-events only on the ticks, so the wide overlay never
    // blocks chat.
    <nav
      aria-label="Conversation"
      className="absolute inset-y-[16%] left-0 z-[6] hidden @[820px]:flex w-[320px] flex-col overflow-y-auto overflow-x-hidden pl-2 pointer-events-none [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
    >
      <ScrollFadeTop />
      <ScrollFadeBottom />
      <div
        ref={bandRef}
        className="relative my-auto flex shrink-0 flex-col items-start py-1 [&>button+button]:mt-[4px]"
      >
        {turnIds.map((id, i) => {
          const active = id === activeId;
          // Brightness ladder mirrors the chat viewport: the turn being read
          // is ink, turns on screen are mid, off-screen history recedes.
          const tone = active ? "bg-ink" : visibleSet.has(id) ? "bg-ink/45" : "bg-ink/20";
          const appeared = !initialIds.current?.has(id);
          return (
            <button
              key={id}
              ref={active ? activeRef : undefined}
              type="button"
              onClick={() => scrollTo(id)}
              aria-current={active ? "true" : undefined}
              aria-label={titles[i] || "Message"}
              className={`pointer-events-auto relative flex h-[9px] scroll-mt-[52px] scroll-mb-[30px] items-center after:absolute after:content-[''] after:-inset-y-[7px] after:-left-2 after:-right-8 ${appeared ? "chat-rail-tick-in" : ""}`}
            >
              <span
                ref={(el) => {
                  ticksRef.current[i] = el;
                }}
                className={`block h-[2px] rounded-full transition-[background-color] duration-panel ${tone}`}
                style={{ width: active ? ACTIVE_W : BASE_W }}
              />
            </button>
          );
        })}
        {/* Same surface dialect as the app's tooltips — the pill floats over
            chat text, so it needs its own material, not bare glyphs. */}
        <div
          ref={labelRef}
          aria-hidden="true"
          className="surface-panel surface-popover pointer-events-none absolute left-11 z-10 max-w-[280px] -translate-y-1/2 truncate px-2 py-1 text-xs text-ink opacity-0"
          style={{ filter: "blur(2px)" }}
        />
      </div>
    </nav>
  );
}
