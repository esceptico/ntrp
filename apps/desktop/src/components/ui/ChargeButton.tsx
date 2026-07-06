import { useEffect, useRef, useState } from "react";

/**
 * Hold-to-confirm where the button's own border is the charge: the full
 * perimeter brightens with hold time — intensity, not a traveling snake —
 * and drains back from wherever it is on release. A full charge arms the
 * action and the label rolls to the receipt, in place. The control is the
 * progress AND the confirmation: no external bar, no dialog, no toast.
 * Extracted from ~/src/interaction-lab's BorderCharge study into a
 * reusable button with an `onArmed` callback (the study fired its own
 * "Cleared" receipt inline; this version calls back so callers can run
 * their own action and choose the armed-label text).
 *
 * Tuned values kept verbatim: WIND_MS 1100 linear border-opacity ramp;
 * drain 500ms cubic-bezier(0.22, 1, 0.36, 1) retargeting from
 * getComputedStyle opacity; arm only if still held at full; label roll
 * 450ms transform + 160ms/260ms blur (roll/land); mask gradient
 * transparent → #000 14%-86% → transparent; revert 1400ms then 300ms
 * fade cubic-bezier(0.2, 0.8, 0.2, 1); transitioncancel fires on
 * retarget — listen for transitionend only.
 */

const WIND_MS = 1100;

export function ChargeButton({
  onArmed,
  label,
  armedLabel,
  windMs = WIND_MS,
}: {
  onArmed: () => void;
  label: string;
  armedLabel: string;
  windMs?: number;
}) {
  const chargeRef = useRef<HTMLSpanElement | null>(null);
  const holdingRef = useRef(false);
  const [armed, setArmed] = useState(false);
  const [rolling, setRolling] = useState(false);
  const revertRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const rollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Motion is defocus: the label is soft while it rolls, sharp at rest —
  // same optics as the rolling digits.
  const rollPulse = () => {
    setRolling(true);
    if (rollRef.current) clearTimeout(rollRef.current);
    // Clear mid-roll so the blur-out finishes as the label lands sharp.
    rollRef.current = setTimeout(() => setRolling(false), 240);
  };

  const arm = () => {
    setArmed(true);
    rollPulse();
    onArmed();
    revertRef.current = setTimeout(() => {
      setArmed(false);
      rollPulse();
      const el = chargeRef.current;
      if (el) {
        el.style.transition = "opacity 300ms cubic-bezier(0.2, 0.8, 0.2, 1)";
        el.style.opacity = "0";
      }
      revertRef.current = null;
    }, 1400);
  };

  const startCharge = () => {
    const el = chargeRef.current;
    if (!el || armed || revertRef.current || holdingRef.current) return;
    holdingRef.current = true;
    el.style.transition = `opacity ${windMs}ms linear`;
    el.style.opacity = "1";
  };

  // Release mid-charge: retarget from the current intensity and drain back
  // on the smooth-out curve. Interruptible, no ceremony.
  const stopCharge = () => {
    if (!holdingRef.current) return;
    holdingRef.current = false;
    const el = chargeRef.current;
    if (!el || armed || revertRef.current) return;
    const cur = getComputedStyle(el).opacity;
    el.style.transition = "none";
    el.style.opacity = cur;
    void el.getBoundingClientRect();
    el.style.transition = "opacity 500ms cubic-bezier(0.22, 1, 0.36, 1)";
    el.style.opacity = "0";
  };

  // Full intensity only counts if still held when the ramp completes — a
  // retargeted (released) transition fires transitioncancel, not end.
  const onTransitionEnd = (e: React.TransitionEvent<HTMLSpanElement>) => {
    if (e.propertyName !== "opacity") return;
    if (holdingRef.current && getComputedStyle(e.currentTarget).opacity === "1") arm();
  };

  useEffect(() => () => {
    if (revertRef.current) clearTimeout(revertRef.current);
    if (rollRef.current) clearTimeout(rollRef.current);
  }, []);

  return (
    <button
      type="button"
      onPointerDown={startCharge}
      onPointerUp={stopCharge}
      onPointerLeave={stopCharge}
      onKeyDown={(e) => { if ((e.key === " " || e.key === "Enter") && !e.repeat) startCharge(); }}
      onKeyUp={stopCharge}
      className="relative select-none touch-none rounded-[10px] bg-surface-soft px-4 py-2 text-[13px] text-ink-soft shadow-[var(--shadow-sm)]"
      aria-live="polite"
    >
      {/* The charge: a full border whose intensity ramps with hold time. */}
      <span
        ref={chargeRef}
        aria-hidden="true"
        onTransitionEnd={onTransitionEnd}
        className="pointer-events-none absolute rounded-[11px] border-[1.5px] border-accent opacity-0"
        style={{ inset: -1 }}
      />
      {/* Fixed-width clip; the label rolls to the receipt on arm. */}
      <span
        className="relative block overflow-hidden text-left"
        style={{
          height: "1.35em",
          maskImage: "linear-gradient(to bottom, transparent, #000 14%, #000 86%, transparent)",
          WebkitMaskImage: "linear-gradient(to bottom, transparent, #000 14%, #000 86%, transparent)",
        }}
      >
        <span
          className="flex flex-col transition-[transform,filter]"
          style={{
            // Blur is continuous, never snapped: it ramps in over the first
            // stretch of the roll and eases out across the landing.
            transitionDuration: rolling ? "450ms, 160ms" : "450ms, 260ms",
            transitionTimingFunction: "cubic-bezier(0.22, 1, 0.36, 1), cubic-bezier(0.2, 0.8, 0.2, 1)",
            transform: armed ? "translateY(-1.35em)" : "translateY(0)",
            filter: rolling ? "blur(1.2px)" : "blur(0)",
          }}
        >
          <span className="h-[1.35em] leading-[1.35] whitespace-nowrap">{label}</span>
          <span className="h-[1.35em] leading-[1.35] whitespace-nowrap text-accent">{armedLabel}</span>
        </span>
      </span>
    </button>
  );
}
