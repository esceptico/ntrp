import { useEffect, useRef, type RefObject } from "react";

/**
 * Ported near-verbatim from ~/src/interaction-lab's TravelingHighlight
 * (FF proximity ideology): the hover highlight is ONE element that travels
 * between rows (easing to the active item) instead of per-row background
 * flips. Fresh-guard: the pill appears IN PLACE on first activation
 * (opacity only) and only travels while already visible. Mount it as a
 * child of the item container (which must be position:relative — the pill
 * positions against it, scroll-aware).
 *
 * watch="focus"    — Radix-style menus: real DOM focus moves between
 *                    menuitems for both pointer and keyboard, so focus is
 *                    the source.
 * watch="selected" — cmdk-style lists: pointer + keyboard unify into
 *                    data-selected, observed via mutations.
 *
 * Distinct from ProximityHighlight (src/components/ui/ProximityHighlight.tsx):
 * that component is a controlled `rect`-driven spring (SPRING_PROXIMITY)
 * used by the app's own popover/select menus and reads a `rect` prop the
 * consumer computes. TravelingHighlight is uncontrolled — it owns its own
 * DOM listeners (focusin/focusout, MutationObserver, scroll) against a
 * `listRef` and drives plain CSS transitions, matching the lab source
 * verbatim rather than routing through the app's spring-based primitive.
 * Kept as a separate port since the brief calls for a faithful port, not a
 * re-derivation onto ProximityHighlight's spring; consolidate later only
 * if a consumer needs both idioms merged.
 *
 * Tuned values kept verbatim from the lab source (token names mapped):
 * travel `top/height var(--duration-travel) var(--ease-smooth-out)`
 * (lab's --duration-fast, 250ms — renamed --duration-travel here since
 * ntrp's own --duration-fast already names a different, 150ms tier),
 * opacity `var(--duration-quick) var(--ease-smooth-out)`; fresh-guard
 * (appear in place, then travel); `focusout` deferred via `queueMicrotask`;
 * MutationObserver on `data-selected` for list mode; scroll repositions
 * without transition.
 */

const TRAVEL =
  "top var(--duration-travel) var(--ease-smooth-out), height var(--duration-travel) var(--ease-smooth-out), opacity var(--duration-quick) var(--ease-smooth-out)";
const FADE = "opacity var(--duration-quick) var(--ease-smooth-out)";

export function TravelingHighlight({
  listRef,
  watch,
  className = "left-0 right-0",
}: {
  listRef: RefObject<HTMLElement | null>;
  watch: "focus" | "selected";
  className?: string;
}) {
  const hlRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const list = listRef.current, hl = hlRef.current;
    if (!list || !hl) return;

    // Returns the item to highlight, null to hide, or "hold" to stay put —
    // Radix parks focus on the menu ROOT while the pointer glides between
    // items; hiding there would reset the fresh-guard and every hover-move
    // would snap instead of travel.
    const resolve = (): HTMLElement | "hold" | null => {
      if (watch === "selected") return list.querySelector<HTMLElement>('[data-selected="true"]');
      const active = document.activeElement;
      if (!(active instanceof HTMLElement) || !list.contains(active)) return null;
      return active.getAttribute("role") === "menuitem" ? active : "hold";
    };

    const update = (travel: boolean) => {
      const active = resolve();
      if (active === "hold") return;
      if (!active) {
        hl.style.opacity = "0";
        return;
      }
      const lr = list.getBoundingClientRect();
      const ar = active.getBoundingClientRect();
      const visible = hl.style.opacity === "1";
      hl.style.transition = travel && visible ? TRAVEL : FADE;
      hl.style.top = `${ar.top - lr.top + list.scrollTop}px`;
      hl.style.height = `${ar.height}px`;
      hl.style.opacity = "1";
    };

    const onMove = () => update(true);
    // focusout fires BEFORE the next focusin — defer the hide check past it
    // so an in-list focus move never resets the fresh-guard mid-travel.
    const onFocusOut = () => queueMicrotask(() => update(true));
    // "hold" can't tell the between-items gap from the pointer leaving the
    // menu — the pointer says so directly.
    const onPointerLeave = () => {
      hl.style.transition = FADE;
      hl.style.opacity = "0";
    };
    const onScroll = () => update(false);
    let mo: MutationObserver | null = null;
    if (watch === "selected") {
      mo = new MutationObserver(onMove);
      mo.observe(list, { subtree: true, attributes: true, attributeFilter: ["data-selected"] });
    } else {
      list.addEventListener("focusin", onMove);
      list.addEventListener("focusout", onFocusOut);
      list.addEventListener("pointerleave", onPointerLeave);
    }
    list.addEventListener("scroll", onScroll, { passive: true });
    update(false);
    return () => {
      mo?.disconnect();
      list.removeEventListener("focusin", onMove);
      list.removeEventListener("focusout", onFocusOut);
      list.removeEventListener("pointerleave", onPointerLeave);
      list.removeEventListener("scroll", onScroll);
    };
  }, [listRef, watch]);

  return (
    <div
      ref={hlRef}
      aria-hidden="true"
      // Fill token mapped from the lab's --panel-fill (not defined in
      // ntrp) to bg-ink/[0.08] — ntrp's existing fill idiom, matching
      // ProximityHighlight's own highlight fill exactly.
      className={`pointer-events-none absolute rounded-[7px] bg-ink/[0.08] opacity-0 ${className}`}
    />
  );
}
