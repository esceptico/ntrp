import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";
import clsx from "clsx";
import {
  AtSign,
  CalendarClock,
  ChevronDown,
  Clock,
  Hash,
  MessageSquare,
} from "lucide-react";
import { EASE_OUT, SPRING_POPOVER, MOTION } from "@/lib/tokens/motion";
import { ICON } from "@/lib/icons";
import { useReanchor } from "@/lib/hooks";
import { Chip } from "@/components/ui/Chip";
import { Input } from "@/components/ui/Input";
import { Tab, Tabs } from "@/components/ui/Tabs";
import { Select } from "@/components/ui/Select";
import { RangeSlider } from "@/components/ui/Slider";

const DAY_MIN = 24 * 60;
/** "HH:MM" → minutes since midnight, or null when empty (no bound). */
const hhmmToMin = (s: string): number | null => {
  if (!s) return null;
  const [h, m] = s.split(":").map(Number);
  return Number.isFinite(h) && Number.isFinite(m) ? h * 60 + m : null;
};
/** minutes → "HH:MM" (DAY_MIN renders as 24:00 but is stored as "" = no bound). */
const minToHhmm = (n: number): string =>
  `${String(Math.floor(n / 60) % 24).padStart(2, "0")}:${String(n % 60).padStart(2, "0")}`;
import { BlurSwap } from "@/components/ui/BlurSwap";
import type { EventType, Schedule, ScheduleKind } from "@/features/automations/lib/schedule";
import { scheduleLabel } from "@/features/automations/lib/schedule";

// ─── Schedule chip + popover ────────────────────────────────────────

export function ScheduleChip({
  schedule,
  onChange,
}: {
  schedule: Schedule;
  onChange: (next: Schedule) => void;
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  // Anchor the portaled popover off the chip's rect. Portaling to <body>
  // lets it escape the editor modal's `overflow-hidden`.
  // Opens above-left: bottom edge above the chip, left edges aligned.
  const [coords, setCoords] = useState<{ bottom: number; left: number } | null>(null);

  useReanchor(open, () => {
    const el = wrapRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    setCoords({ bottom: window.innerHeight - r.top + 6, left: r.left });
  });

  // The popover is portaled outside `wrapRef`, so accept clicks inside
  // either the trigger or the popover; anything else dismisses.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (wrapRef.current?.contains(t)) return;
      if (popoverRef.current?.contains(t)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  return (
    <div ref={wrapRef} className="relative">
      <Chip
        size="md"
        active={open}
        leading={
          <BlurSwap swapKey={schedule.kind === "message" ? "message" : "time"}>
            {schedule.kind === "message" ? (
              <MessageSquare size={ICON.XS} strokeWidth={2} />
            ) : (
              <Clock size={ICON.XS} strokeWidth={2} />
            )}
          </BlurSwap>
        }
        trailing={<ChevronDown size={ICON.XS} strokeWidth={2} className="opacity-60" />}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="truncate max-w-[210px]">{scheduleLabel(schedule)}</span>
      </Chip>

      {createPortal(
        <AnimatePresence>
          {open && coords && (
            <motion.div
              ref={popoverRef}
              initial={{ opacity: 0, scale: 0.97, y: 4 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{
                opacity: 0,
                scale: 0.97,
                y: 2,
                transition: { duration: MOTION.fast, ease: EASE_OUT },
              }}
              transition={SPRING_POPOVER}
              style={{
                position: "fixed",
                bottom: coords.bottom,
                left: coords.left,
                // Inside #app, ABOVE the automations modal (--z-modal 50) but
                // BELOW the popover tier (--z-popover 60), so a nested Select's
                // listbox (--z-popover) layers ABOVE this by z-index — robustly,
                // not relying on portal DOM order.
                zIndex: "var(--z-modal-top)",
                transformOrigin: "bottom left",
              }}
              className="surface-panel surface-popover w-[340px] grid gap-3 p-3"
            >
              <Tabs variant="segmented"
                size="sm"
                value={schedule.kind}
                onChange={(kind) => onChange({ ...schedule, kind: kind as ScheduleKind })}
              >
                <Tab value="at">Time</Tab>
                <Tab value="every">Every</Tab>
                <Tab value="event">Event</Tab>
                <Tab value="message">Message</Tab>
              </Tabs>

              <div className="grid">
                <div
                  aria-hidden={schedule.kind !== "at" || undefined}
                  className={fieldStackCls(schedule.kind === "at")}
                >
                  <ScheduleField label="At">
                    <Input
                      type="time"
                      value={schedule.at}
                      onChange={(e) => onChange({ ...schedule, at: e.target.value })}
                      className="tabular-nums"
                    />
                  </ScheduleField>
                  <ScheduleField label="Days" hint="daily · weekdays · mon,fri">
                    <Input
                      value={schedule.days}
                      onChange={(e) => onChange({ ...schedule, days: e.target.value })}
                      placeholder="daily"
                      spellCheck={false}
                      className="tabular-nums"
                    />
                  </ScheduleField>
                </div>

                <div
                  aria-hidden={schedule.kind !== "every" || undefined}
                  className={fieldStackCls(schedule.kind === "every")}
                >
                  <ScheduleField label="Interval" hint="30m · 2h · 1d · 2d12h">
                    <Input
                      value={schedule.every}
                      onChange={(e) => onChange({ ...schedule, every: e.target.value })}
                      placeholder="30m"
                      spellCheck={false}
                      className="tabular-nums"
                    />
                  </ScheduleField>
                  <ScheduleField label="Days" hint="daily · weekdays · mon,fri">
                    <Input
                      value={schedule.days}
                      onChange={(e) => onChange({ ...schedule, days: e.target.value })}
                      placeholder="weekdays"
                      spellCheck={false}
                      className="tabular-nums"
                    />
                  </ScheduleField>
                  <ScheduleField label="Active window" hint="optional — only run within these hours">
                    <RangeSlider
                      aria-label="Active window"
                      min={0}
                      max={DAY_MIN}
                      step={15}
                      value={[hhmmToMin(schedule.start) ?? 0, hhmmToMin(schedule.end) ?? DAY_MIN]}
                      onChange={([lo, hi]) =>
                        onChange({
                          ...schedule,
                          start: lo <= 0 ? "" : minToHhmm(lo),
                          end: hi >= DAY_MIN ? "" : minToHhmm(hi),
                        })
                      }
                      formatValue={(n) => (n >= DAY_MIN ? "24:00" : minToHhmm(n))}
                      className="pt-1"
                    />
                  </ScheduleField>
                </div>

                <div
                  aria-hidden={schedule.kind !== "event" || undefined}
                  className={fieldStackCls(schedule.kind === "event")}
                >
                  <ScheduleField label="Event">
                    <Select
                      value={schedule.event}
                      onChange={(v) => onChange({ ...schedule, event: v as EventType })}
                      options={[
                        { value: "starts", label: "starts" },
                        { value: "ends", label: "ends" },
                        { value: "approaching", label: "approaching" },
                      ]}
                      aria-label="Event"
                      className="w-full"
                    />
                  </ScheduleField>
                  {schedule.event === "approaching" && (
                    <ScheduleField label="Lead time" hint="minutes before the event">
                      <Input
                        value={schedule.lead}
                        onChange={(e) => onChange({ ...schedule, lead: e.target.value })}
                        placeholder="15"
                        spellCheck={false}
                        className="tabular-nums"
                      />
                    </ScheduleField>
                  )}
                </div>

                <div
                  aria-hidden={schedule.kind !== "message" || undefined}
                  className={fieldStackCls(schedule.kind === "message")}
                >
                  <ScheduleField label="Channels" hint="one or more, comma-separated">
                    <div className="relative">
                      <Hash
                        size={ICON.XS}
                        strokeWidth={2}
                        className="absolute left-2 top-1/2 -translate-y-1/2 text-faint pointer-events-none"
                      />
                      <Input
                        value={schedule.channel}
                        onChange={(e) => onChange({ ...schedule, channel: e.target.value })}
                        placeholder="feel-good-inc, eng-bugs"
                        spellCheck={false}
                        className="!pl-7 tabular-nums"
                      />
                    </div>
                  </ScheduleField>
                  <ScheduleField label="From user" hint="optional — only this sender">
                    <div className="relative">
                      <AtSign
                        size={ICON.XS}
                        strokeWidth={2}
                        className="absolute left-2 top-1/2 -translate-y-1/2 text-faint pointer-events-none"
                      />
                      <Input
                        value={schedule.fromUser}
                        onChange={(e) => onChange({ ...schedule, fromUser: e.target.value })}
                        placeholder="username"
                        spellCheck={false}
                        className="!pl-7 tabular-nums"
                      />
                    </div>
                  </ScheduleField>
                  <ScheduleField label="Keywords" hint="optional, any of — bug, error, broken">
                    <Input
                      value={schedule.keywords}
                      onChange={(e) => onChange({ ...schedule, keywords: e.target.value })}
                      placeholder="bug, error"
                      spellCheck={false}
                      className="tabular-nums"
                    />
                  </ScheduleField>
                </div>
              </div>

              <div className="flex items-center gap-1.5 pt-2.5 border-t border-line-soft text-xs text-faint">
                <BlurSwap swapKey={schedule.kind === "message" ? "message" : "time"}>
                  {schedule.kind === "message" ? (
                    <MessageSquare size={ICON.XS} strokeWidth={2} />
                  ) : (
                    <CalendarClock size={ICON.XS} strokeWidth={2} />
                  )}
                </BlurSwap>
                <span className="truncate">{scheduleLabel(schedule)}</span>
              </div>
          </motion.div>
          )}
        </AnimatePresence>,
        document.querySelector("#app") ?? document.body,
      )}
    </div>
  );
}

// ─── Atoms ──────────────────────────────────────────────────────────

// All trigger-kind panels share one grid cell ([grid-area:1/1]) so the popover
// is always as tall as the tallest panel — switching kinds can't change its
// height (no jump). Inactive panels stay laid out (for sizing) but hidden.
// Both states carry the opacity transition so the swap overlaps (outgoing
// dissolves while incoming rises); the inactive panel's visibility flip is
// delayed past the fade so it never cuts out mid-crossfade.
const fieldStackCls = (active: boolean) =>
  clsx(
    "[grid-area:1/1] grid gap-2.5 content-start",
    active
      ? "opacity-100 transition-opacity duration-row ease-out"
      : "invisible opacity-0 pointer-events-none [transition:opacity_var(--duration-row)_var(--ease-out-soft),visibility_0s_var(--duration-row)]",
  );

function ScheduleField({
  label,
  hint,
  className,
  children,
}: {
  label: string;
  /** Optional one-line example/format hint shown below the input. Keep it
   *  to ~40 chars — anything longer wraps awkwardly in the 2-col grid. */
  hint?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <label className={clsx("grid gap-1", className)}>
      <span className="text-2xs font-medium uppercase tracking-[0.06em] text-muted">{label}</span>
      {children}
      {hint && (
        <span className="text-2xs text-faint font-mono leading-snug">{hint}</span>
      )}
    </label>
  );
}
