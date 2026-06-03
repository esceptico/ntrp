import { useEffect, useRef, useState } from "react";
import BlurEffect from "react-progressive-blur";

/**
 * Scroll-edge blur for modal/list panes. Pinned to the top of the scroll
 * viewport with `position: sticky` so the blur's backdrop stays the live,
 * scrolling page. A transform-based pin (translateY by scrollTop) turns the
 * wrapper into a backdrop root and the blur samples nothing — only a flat veil.
 */
export function ScrollBlurTop() {
  const sentinelRef = useRef<HTMLDivElement>(null);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const el = sentinelRef.current;
    const scroller = el?.parentElement;
    if (!el || !scroller) return;
    // Sticky pins inside the content box; offset by the scroller's top padding
    // so the band lands at the padding-box top (the visual pane edge), not
    // below the content inset.
    el.style.top = `calc(-1 * ${getComputedStyle(scroller).paddingTop})`;
    const onScroll = () => {
      const next = scroller.scrollTop > 0;
      setScrolled((prev) => (prev === next ? prev : next));
    };
    onScroll();
    scroller.addEventListener("scroll", onScroll, { passive: true });
    return () => scroller.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div
      ref={sentinelRef}
      aria-hidden
      className="scroll-progressive-blur-top"
      data-scrolled={scrolled ? "true" : "false"}
    >
      <BlurEffect
        className="scroll-progressive-blur-layer"
        intensity={72}
        position="top"
      />
    </div>
  );
}
