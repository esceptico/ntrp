import type { CSSProperties } from "react";
import { useEffect, useRef, useState } from "react";

/**
 * Cheap scroll-edge fade for modal/list panes. This does not paint a
 * color overlay; it toggles a mask on the scroll parent so the content
 * itself fades out at the top edge.
 */
export function ScrollBlurTop() {
  const ref = useRef<HTMLDivElement>(null);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const el = ref.current;
    const scroller = el?.parentElement;
    if (!scroller) return;
    const onScroll = () => {
      const next = scroller.scrollTop > 0;
      setScrolled(next);
      scroller.classList.toggle("scroll-mask-top", next);
    };
    onScroll();
    scroller.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      scroller.classList.remove("scroll-mask-top");
      scroller.removeEventListener("scroll", onScroll);
    };
  }, []);

  return (
    <div
      ref={ref}
      aria-hidden
      className="scroll-mask-top-sentinel"
      data-scrolled={scrolled ? "true" : "false"}
    />
  );
}

interface ProgressiveBlurOverlayProps {
  edge: "top" | "bottom";
  className?: string;
  style?: CSSProperties;
}

export function ProgressiveBlurOverlay({
  edge,
  className = "",
  style,
}: ProgressiveBlurOverlayProps) {
  return (
    <div
      aria-hidden
      className={`progressive-blur progressive-blur-${edge} ${className}`.trim()}
      style={style}
    >
      <div /><div /><div />
    </div>
  );
}
