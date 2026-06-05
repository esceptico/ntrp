import { useEffect, useRef, useState, type RefObject } from "react";
import BlurEffect from "react-progressive-blur";

/**
 * Progressive blur for scroll panes without a transformed surface-panel
 * ancestor (main chat). Rendered outside the scrolled content flow so the
 * band stays pinned to the pane top even when the history is short.
 */
export function ScrollBlurTop({ scrollerRef }: { scrollerRef: RefObject<HTMLElement | null> }) {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const scroller = scrollerRef.current;
    if (!scroller) return;

    const onScroll = () => {
      const next = scroller.scrollTop > 0;
      setScrolled((prev) => (prev === next ? prev : next));
    };
    onScroll();
    scroller.addEventListener("scroll", onScroll, { passive: true });
    return () => scroller.removeEventListener("scroll", onScroll);
  }, [scrollerRef]);

  return (
    <div
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
