import { useCallback, useRef } from "react";
import { useStore } from "../store";

// Registration-grid empty state. A faint dot grid sits behind a centered
// crosshair + copy; a soft radial spotlight follows the pointer over the
// surface. The spotlight is driven by CSS variables (--mx / --my) written
// straight to the wrapper element on pointermove — no React state, no rAF
// loop. prefers-reduced-motion neutralizes the spotlight via styles.css.
export function EmptyState() {
  const connected = useStore((s) => s.connected);
  const wrapRef = useRef<HTMLDivElement | null>(null);

  const onPointerMove = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const el = wrapRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    el.style.setProperty("--mx", `${e.clientX - rect.left}px`);
    el.style.setProperty("--my", `${e.clientY - rect.top}px`);
  }, []);

  const onPointerLeave = useCallback(() => {
    const el = wrapRef.current;
    if (!el) return;
    el.style.removeProperty("--mx");
    el.style.removeProperty("--my");
  }, []);

  return (
    <div
      ref={wrapRef}
      onPointerMove={onPointerMove}
      onPointerLeave={onPointerLeave}
      className="empty-state mt-[14vh] relative grid place-items-center text-center"
    >
      <div className="empty-state-grid" aria-hidden />
      <div className="empty-state-spotlight" aria-hidden />
      <div className="relative grid gap-5 justify-items-center">
        <span aria-hidden className="empty-state-crosshair">
          <svg viewBox="0 0 24 24" width="24" height="24" fill="none">
            <circle cx="12" cy="12" r="3.25" />
            <path d="M12 1.5 V7" />
            <path d="M12 17 V22.5" />
            <path d="M1.5 12 H7" />
            <path d="M17 12 H22.5" />
          </svg>
        </span>
        <div className="grid gap-1.5 max-w-[420px]">
          <h2 className="m-0 text-[20px] font-semibold tracking-[-0.018em] text-ink">
            {connected ? "What's on your mind?" : "Connect to get started"}
          </h2>
          <p className="m-0 text-[13px] text-muted leading-snug">
            {connected
              ? "Send a message, or press ⌘K to search memory, agents, and tools."
              : "Open settings to point ntrp at your server."}
          </p>
        </div>
      </div>
    </div>
  );
}
