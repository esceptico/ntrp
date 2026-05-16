import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";
import { CalendarClock, ChevronDown, Clock, RotateCcw, X } from "lucide-react";
import clsx from "clsx";
import { createAutomation, updateAutomation } from "../../actions";
import type {
  Automation,
  CreateAutomationPayload,
  UpdateAutomationPayload,
} from "../../api";
import { SPRING_SMOOTH } from "../../lib/motion";
import { ICON } from "../../lib/icons";
import { GlassToggle } from "../GlassToggle";

const MODAL_BACKDROP_DURATION = 0.2;
const MODAL_EASE = [0.2, 0.8, 0.2, 1] as const;

export type EditorSeed =
  | { kind: "create"; preset?: CreateAutomationPayload }
  | { kind: "edit"; automation: Automation };

type ScheduleKind = "at" | "every" | "event";
type EventType = "starts" | "ends" | "approaching";

interface Schedule {
  kind: ScheduleKind;
  at: string;
  every: string;
  days: string;
  start: string;
  end: string;
  event: EventType;
  lead: string;
}

const DEFAULT_SCHEDULE: Schedule = {
  kind: "at",
  at: "09:00",
  every: "30m",
  days: "daily",
  start: "",
  end: "",
  event: "approaching",
  lead: "15",
};

interface FormState {
  name: string;
  prompt: string;
  schedule: Schedule;
  writable: boolean;
}

function emptyForm(): FormState {
  return { name: "", prompt: "", schedule: { ...DEFAULT_SCHEDULE }, writable: false };
}

function formFromPreset(p: CreateAutomationPayload): FormState {
  const f = emptyForm();
  f.name = p.name ?? "";
  f.prompt = p.description ?? "";
  if (p.writable) f.writable = true;
  if (p.trigger_type === "event") {
    f.schedule = {
      ...f.schedule,
      kind: "event",
      event: (p.event_type as EventType) ?? "approaching",
      lead: p.lead_minutes != null ? String(p.lead_minutes) : f.schedule.lead,
    };
  } else if (p.every) {
    f.schedule = {
      ...f.schedule,
      kind: "every",
      every: p.every,
      days: p.days ?? "",
      start: p.start ?? "",
      end: p.end ?? "",
    };
  } else if (p.at) {
    f.schedule = { ...f.schedule, kind: "at", at: p.at, days: p.days ?? "" };
  }
  return f;
}

function formFromAutomation(a: Automation): FormState {
  const t = a.triggers[0];
  const f = emptyForm();
  f.name = a.name;
  f.prompt = a.description;
  f.writable = a.writable;
  if (!t) return f;
  if (t.type === "time" && t.every) {
    f.schedule = {
      ...f.schedule,
      kind: "every",
      every: t.every,
      days: t.days ?? "",
      start: t.start ?? "",
      end: t.end ?? "",
    };
  } else if (t.type === "time" && t.at) {
    f.schedule = { ...f.schedule, kind: "at", at: t.at, days: t.days ?? "" };
  } else if (t.type === "event") {
    f.schedule = {
      ...f.schedule,
      kind: "event",
      event: (t.event_type as EventType) ?? "approaching",
      lead: t.lead_minutes != null ? String(t.lead_minutes) : f.schedule.lead,
    };
  }
  return f;
}

function buildPayload(f: FormState): CreateAutomationPayload {
  const p: CreateAutomationPayload = {
    name: f.name.trim() || "Untitled automation",
    description: f.prompt.trim(),
    writable: f.writable,
  };
  const s = f.schedule;
  if (s.kind === "at") {
    p.trigger_type = "time";
    p.at = s.at;
    if (s.days) p.days = s.days;
  } else if (s.kind === "every") {
    p.trigger_type = "time";
    p.every = s.every;
    if (s.days) p.days = s.days;
    if (s.start) p.start = s.start;
    if (s.end) p.end = s.end;
  } else {
    p.trigger_type = "event";
    p.event_type = s.event;
    if (s.lead) p.lead_minutes = s.lead;
  }
  return p;
}

function scheduleLabel(s: Schedule): string {
  if (s.kind === "at") {
    const time = formatTime12(s.at);
    const days = humanDays(s.days);
    return days ? `${days} at ${time}` : `Daily at ${time}`;
  }
  if (s.kind === "every") {
    const win = s.start && s.end ? ` (${formatTime12(s.start)}–${formatTime12(s.end)})` : "";
    const days = humanDays(s.days);
    return `Every ${s.every}${win}${days ? ` · ${days}` : ""}`;
  }
  const lead = s.event === "approaching" && s.lead ? ` (${s.lead}m)` : "";
  return `On event ${s.event}${lead}`;
}

function humanDays(days: string): string {
  const v = days.trim().toLowerCase();
  if (!v) return "";
  if (v === "daily" || v === "*") return "Daily";
  if (v === "weekdays") return "Weekdays";
  if (v === "weekends") return "Weekends";
  return days;
}

function formatTime12(hhmm: string): string {
  const m = hhmm.match(/^(\d{1,2}):(\d{2})$/);
  if (!m) return hhmm;
  const hour = Number(m[1]);
  const period = hour >= 12 ? "PM" : "AM";
  const h12 = ((hour + 11) % 12) + 1;
  return `${h12}:${m[2]} ${period}`;
}

export function AutomationEditor({
  seed,
  onClose,
}: {
  seed: EditorSeed | null;
  onClose: () => void;
}) {
  const [form, setForm] = useState<FormState>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const open = !!seed;

  // (Re)hydrate the form whenever a new seed arrives.
  useEffect(() => {
    if (!seed) return;
    if (seed.kind === "edit") setForm(formFromAutomation(seed.automation));
    else if (seed.preset) setForm(formFromPreset(seed.preset));
    else setForm(emptyForm());
    setError(null);
  }, [seed]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if ((e.metaKey || e.ctrlKey) && e.key === "Enter") void submit();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const valid = form.prompt.trim().length > 0;

  const submit = async () => {
    if (!valid || saving || !seed) return;
    setSaving(true);
    setError(null);
    try {
      const payload = buildPayload(form);
      if (seed.kind === "edit") {
        const patch: UpdateAutomationPayload = { ...payload };
        await updateAutomation(seed.automation.task_id, patch);
      } else {
        await createAutomation(payload);
      }
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  const reset = () => {
    if (!seed) return;
    if (seed.kind === "edit") setForm(formFromAutomation(seed.automation));
    else if (seed.preset) setForm(formFromPreset(seed.preset));
    else setForm(emptyForm());
  };

  const root = document.querySelector("#app");
  if (!root) return null;

  return createPortal(
    <AnimatePresence>
      {open && seed && (
        <motion.div
          key="automation-editor"
          className="absolute inset-0 z-[60] grid place-items-center p-8 bg-[rgba(0,0,0,0.36)] backdrop-blur-md"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: MODAL_BACKDROP_DURATION, ease: MODAL_EASE }}
          onClick={onClose}
        >
          <motion.div
            className="auto-editor w-[min(640px,calc(100vw-80px))] max-h-[calc(100vh-80px)] grid grid-rows-[auto_minmax(0,1fr)_auto] rounded-[18px] bg-surface shadow-[var(--shadow-pop)] overflow-hidden border border-line-soft"
            initial={{ opacity: 0, scale: 0.96, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 8 }}
            transition={SPRING_SMOOTH}
            onClick={(e) => e.stopPropagation()}
          >
            <header className="flex items-center justify-between gap-2 px-5 pt-4 pb-2">
              <input
                value={form.name}
                onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
                placeholder="Untitled automation"
                spellCheck={false}
                autoFocus={seed.kind === "create" && !seed.preset}
                className="flex-1 min-w-0 h-7 bg-transparent border-0 text-lg font-semibold tracking-[-0.012em] text-ink outline-none placeholder:text-faint"
              />
              <div className="flex items-center gap-0.5 text-faint">
                <button
                  type="button"
                  onClick={reset}
                  title="Reset"
                  aria-label="Reset"
                  className="grid place-items-center w-7 h-7 rounded-md hover:bg-surface-soft hover:text-ink transition-colors"
                >
                  <RotateCcw size={ICON.MD} strokeWidth={2} />
                </button>
                <button
                  type="button"
                  onClick={onClose}
                  title="Close"
                  aria-label="Close"
                  className="grid place-items-center w-7 h-7 rounded-md hover:bg-surface-soft hover:text-ink transition-colors"
                >
                  <X size={ICON.MD} strokeWidth={2} />
                </button>
              </div>
            </header>

            <div className="px-5 pb-2 grid grid-rows-[minmax(0,1fr)] min-h-0">
              <textarea
                value={form.prompt}
                onChange={(e) => setForm((p) => ({ ...p, prompt: e.target.value }))}
                placeholder="What should the agent do when this automation fires?"
                spellCheck={false}
                rows={6}
                className="w-full h-full min-h-[180px] resize-none bg-transparent border-0 text-md leading-[1.6] text-ink tracking-[-0.005em] outline-none placeholder:text-faint"
              />
            </div>

            {error && (
              <div className="mx-5 mb-3 grid gap-0.5 px-3 py-2.5 rounded-[10px] bg-bad-soft border border-[rgba(184,68,43,0.16)]">
                <strong className="text-bad text-sm font-semibold">Couldn't save</strong>
                <span className="text-sm text-[#8a3220] leading-[1.4]">{error}</span>
              </div>
            )}

            <footer className="flex items-center justify-between gap-2 px-3 py-2.5 bg-surface-soft/40">
              <div className="flex items-center gap-2">
                <ScheduleChip
                  schedule={form.schedule}
                  onChange={(schedule) => setForm((p) => ({ ...p, schedule }))}
                />
                <label className="inline-flex items-center gap-1.5 px-1 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={form.writable}
                    onChange={(e) => setForm((p) => ({ ...p, writable: e.target.checked }))}
                    className="size-3 accent-accent"
                  />
                  <span className="text-sm text-muted">Writable</span>
                </label>
              </div>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={onClose}
                  className="inline-flex items-center h-8 px-3 rounded-[9px] text-sm font-medium text-muted hover:text-ink transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => void submit()}
                  disabled={!valid || saving}
                  className="inline-flex items-center gap-1.5 h-8 px-3.5 rounded-[9px] bg-ink text-on-ink text-sm font-medium tracking-[-0.005em] hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-opacity"
                >
                  {saving ? "Saving…" : seed.kind === "edit" ? "Save" : "Create"}
                </button>
              </div>
            </footer>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    root,
  );
}

// ─── Schedule chip + popover ────────────────────────────────────────

function ScheduleChip({
  schedule,
  onChange,
}: {
  schedule: Schedule;
  onChange: (next: Schedule) => void;
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  return (
    <div ref={wrapRef} className="relative">
      <Chip
        active={open}
        icon={<Clock size={ICON.XS} strokeWidth={2} />}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="truncate max-w-[210px]">{scheduleLabel(schedule)}</span>
        <ChevronDown size={ICON.XS} strokeWidth={2} className="opacity-60 shrink-0" />
      </Chip>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 6, scale: 0.98 }}
            transition={{ duration: 0.16, ease: MODAL_EASE }}
            className="absolute bottom-[calc(100%+6px)] left-0 z-10 w-[300px] grid gap-3 p-3 rounded-[12px] border border-line-soft bg-surface shadow-[var(--shadow-pop)]"
          >
            <GlassToggle
              size="sm"
              value={schedule.kind}
              onChange={(kind) => onChange({ ...schedule, kind: kind as ScheduleKind })}
              options={[
                { value: "at", label: "At time" },
                { value: "every", label: "Every" },
                { value: "event", label: "On event" },
              ]}
            />

            {schedule.kind === "at" && (
              <div className="grid grid-cols-2 gap-2">
                <ScheduleField label="At">
                  <input
                    type="time"
                    value={schedule.at}
                    onChange={(e) => onChange({ ...schedule, at: e.target.value })}
                    className={schedFieldCls}
                  />
                </ScheduleField>
                <ScheduleField label="Days" hint="daily · weekdays · mon,fri">
                  <input
                    value={schedule.days}
                    onChange={(e) => onChange({ ...schedule, days: e.target.value })}
                    placeholder="daily"
                    spellCheck={false}
                    className={schedFieldCls}
                  />
                </ScheduleField>
              </div>
            )}

            {schedule.kind === "every" && (
              <div className="grid grid-cols-2 gap-2">
                <ScheduleField label="Interval" hint="30m · 2h · 1d · 2d12h">
                  <input
                    value={schedule.every}
                    onChange={(e) => onChange({ ...schedule, every: e.target.value })}
                    placeholder="30m"
                    spellCheck={false}
                    className={schedFieldCls}
                  />
                </ScheduleField>
                <ScheduleField label="Days" hint="daily · weekdays · mon,fri">
                  <input
                    value={schedule.days}
                    onChange={(e) => onChange({ ...schedule, days: e.target.value })}
                    placeholder="weekdays"
                    spellCheck={false}
                    className={schedFieldCls}
                  />
                </ScheduleField>
                <ScheduleField label="Start">
                  <input
                    type="time"
                    value={schedule.start}
                    onChange={(e) => onChange({ ...schedule, start: e.target.value })}
                    className={schedFieldCls}
                  />
                </ScheduleField>
                <ScheduleField label="End">
                  <input
                    type="time"
                    value={schedule.end}
                    onChange={(e) => onChange({ ...schedule, end: e.target.value })}
                    className={schedFieldCls}
                  />
                </ScheduleField>
              </div>
            )}

            {schedule.kind === "event" && (
              <div className="grid grid-cols-2 gap-2">
                <ScheduleField label="Event">
                  <select
                    value={schedule.event}
                    onChange={(e) => onChange({ ...schedule, event: e.target.value as EventType })}
                    className={schedFieldCls}
                  >
                    <option value="starts">starts</option>
                    <option value="ends">ends</option>
                    <option value="approaching">approaching</option>
                  </select>
                </ScheduleField>
                {schedule.event === "approaching" && (
                  <ScheduleField label="Lead (m)">
                    <input
                      value={schedule.lead}
                      onChange={(e) => onChange({ ...schedule, lead: e.target.value })}
                      placeholder="15"
                      spellCheck={false}
                      className={schedFieldCls}
                    />
                  </ScheduleField>
                )}
              </div>
            )}

            <div className="flex items-center gap-1 pt-1 text-xs text-faint">
              <CalendarClock size={ICON.XS} strokeWidth={2} />
              <span className="truncate">{scheduleLabel(schedule)}</span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── Atoms ──────────────────────────────────────────────────────────

const schedFieldCls =
  "w-full h-8 px-2 border border-line rounded-md bg-surface text-ink text-sm tabular-nums outline-none hover:border-line-strong focus:border-accent focus:shadow-[0_0_0_3px_var(--color-accent-soft)] transition-[border-color,box-shadow]";

function ScheduleField({
  label,
  hint,
  children,
}: {
  label: string;
  /** Optional one-line example/format hint shown below the input. Keep it
   *  to ~40 chars — anything longer wraps awkwardly in the 2-col grid. */
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="grid gap-1">
      <span className="text-2xs font-medium uppercase tracking-[0.06em] text-muted">{label}</span>
      {children}
      {hint && (
        <span className="text-2xs text-faint font-mono leading-snug">{hint}</span>
      )}
    </label>
  );
}

function Chip({
  icon,
  children,
  active,
  onClick,
  title,
}: {
  icon: React.ReactNode;
  children: React.ReactNode;
  active?: boolean;
  onClick?: () => void;
  title?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className={clsx(
        "inline-flex items-center gap-1.5 h-8 px-2.5 rounded-[8px] text-sm font-medium tracking-[-0.005em] transition-colors select-none",
        active
          ? "bg-surface text-ink shadow-[var(--shadow-sm)] border border-line-soft"
          : "bg-transparent text-muted hover:bg-surface hover:text-ink border border-transparent",
      )}
    >
      <span className={clsx("shrink-0", active ? "text-accent-strong" : "text-faint")}>{icon}</span>
      {children}
    </button>
  );
}
