import { useEffect, useRef, useState } from "react";

/**
 * Progressive backdrop blur on scroll top — content blurs heavily at
 * the top of the scroll viewport and fades to clear below, with the
 * effective blur RADIUS varying smoothly across the strip (not just
 * its opacity). 7 stacked `backdrop-filter` layers with progressively
 * smaller blur radii (16 → 0.5 px), each masked to an overlapping
 * band so the active blur radius slides as you move down.
 *
 * Visibility is gated on scrollTop > 0 — at the top of the scroll
 * viewport the strip is fully invisible (opacity 0) to avoid the
 * Chromium compositor-layer artifact where backdrop-filter on
 * uniform bg still produces a faint visible rectangle. The strip
 * fades in as soon as content begins to scroll past it, which is
 * also the only moment the effect is meaningful.
 *
 * Linen-mode only. Glass-mode falls through to nothing — the modal
 * slab's own backdrop-filter handles separation, and nesting more
 * inside would hit the containing-block trap.
 *
 * Render as the FIRST child of the scrolling container.
 */
export function ScrollBlurTop() {
  const ref = useRef<HTMLDivElement>(null);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const el = ref.current;
    const scroller = el?.parentElement;
    if (!scroller) return;
    const onScroll = () => setScrolled(scroller.scrollTop > 0);
    onScroll();
    scroller.addEventListener("scroll", onScroll, { passive: true });
    return () => scroller.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div
      ref={ref}
      aria-hidden
      className="scroll-blur-top"
      data-scrolled={scrolled ? "true" : "false"}
    >
      <div /><div /><div /><div /><div /><div /><div />
    </div>
  );
}
