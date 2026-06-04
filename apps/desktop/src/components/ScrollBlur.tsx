import { useEffect, useRef, useState } from "react";
import BlurEffect from "react-progressive-blur";

/**
 * Progressive blur for scroll panes without a transformed surface-panel
 * ancestor (main chat). Pinned with sticky so backdrop-filter samples the
 * live scrolling content.
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

/**
 * Mask-based scroll-edge fade for surface panels (modals, sidebars, command
 * palette). backdrop-filter breaks inside composited .surface-panel layers;
 * a painted overlay bleeds past rounded panel corners — masking the scroller
 * keeps the fade inside its box.
 */
export function ScrollFadeTop() {
  const sentinelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const scroller = sentinelRef.current?.parentElement;
    if (!scroller) return;

    const onScroll = () => {
      scroller.dataset.scrollFadeTop = scroller.scrollTop > 0 ? "true" : "false";
    };
    onScroll();
    scroller.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      scroller.removeEventListener("scroll", onScroll);
      delete scroller.dataset.scrollFadeTop;
    };
  }, []);

  return <div ref={sentinelRef} aria-hidden className="hidden" />;
}
