import { useEffect, useLayoutEffect, useRef, useState } from "react";
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
  RotateCcw,
  TriangleAlert,
  X,
} from "lucide-react";
import { createAutomation, updateAutomation } from "../../actions";
import type {
  Automation,
  AutomationTrigger,
  CreateAutomationPayload,
  UpdateAutomationPayload,
} from "../../api";
import {
  ENTRY_GLASS,
  ENTRY_LINEN,
  EASE_DECELERATE,
  EASE_OUT,
  SPRING_POPOVER,
  MOTION,
} from "../../lib/tokens/motion";
import { useStore } from "../../store";
import { ICON } from "../../lib/icons";
import { IconButton } from "../IconButton";
import { GlassToggle } from "../GlassToggle";
import { Chip } from "../Chip";
import { GlassSwitch } from "../GlassSwitch";

const MODAL_BACKDROP_DURATION = 0.2;

export type EditorSeed =
  | { kind: "create"; preset?: CreateAutomationPayload }
  | { kind: "edit"; automation: Automation };

type ScheduleKind = "at" | "every" | "event" | "message";
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
  /** Message trigger (Slack watcher). Source is fixed to "slack" in v1.
   *  We collect display names here; the server resolves them to ids at save. */
  channel: string;
  fromUser: string;
  /** Raw comma-separated keywords; split into a `contains` any-of list on save. */
  keywords: string;
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
  channel: "",
  fromUser: "",
  keywords: "",
};

function splitKeywords(raw: string): string[] {
  return raw
    .split(",")
    .map((k) => k.trim())
    .filter(Boolean);
}

interface FormState {
  name: string;
  prompt: string;
  schedule: Schedule;
  auto_approve: boolean;
  /** Rides along from a "Suggested for you" preset so the create payload can
   *  tell the server which suggestion to mark accepted. Editing fields never
   *  clears it; an `edit` seed never sets it. */
  from_suggestion_id?: string;
}

function emptyForm(): FormState {
  return { name: "", prompt: "", schedule: { ...DEFAULT_SCHEDULE }, auto_approve: false };
}

export function formFromPreset(p: CreateAutomationPayload): FormState {
  const f = emptyForm();
  f.name = p.name ?? "";
  f.prompt = p.description ?? "";
  f.from_suggestion_id = p.from_suggestion_id;
  if (p.auto_approve) f.auto_approve = true;
  const msg = p.trigger_type === "message" ? p.triggers?.[0] : undefined;
  if (msg && msg.type === "message") {
    f.schedule = {
      ...f.schedule,
      kind: "message",
      channel: msg.channel_name ?? msg.channel ?? "",
      fromUser: msg.from_user_name ?? msg.from_user ?? "",
      keywords: (msg.contains ?? []).join(", "),
    };
  } else if (p.trigger_type === "event") {
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
  f.auto_approve = a.auto_approve;
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
  } else if (t.type === "message") {
    f.schedule = {
      ...f.schedule,
      kind: "message",
      channel: t.channel_name ?? t.channel ?? "",
      fromUser: t.from_user_name ?? t.from_user ?? "",
      keywords: (t.contains ?? []).join(", "),
    };
  }
  return f;
}

export function buildPayload(f: FormState): CreateAutomationPayload {
  const p: CreateAutomationPayload = {
    name: f.name.trim() || "Untitled automation",
    description: f.prompt.trim(),
    auto_approve: f.auto_approve,
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
  } else if (s.kind === "message") {
    p.trigger_type = "message";
    const trigger: AutomationTrigger = {
      type: "message",
      source: "slack",
      channel: s.channel.trim(),
    };
    const fromUser = s.fromUser.trim();
    if (fromUser) trigger.from_user = fromUser;
    const contains = splitKeywords(s.keywords);
    if (contains.length) trigger.contains = contains;
    p.triggers = [trigger];
  } else {
    p.trigger_type = "event";
    p.event_type = s.event;
    if (s.lead) p.lead_minutes = s.lead;
  }
  if (f.from_suggestion_id) p.from_suggestion_id = f.from_suggestion_id;
  return p;
}

function scheduleLabel(s: Schedule): string {
  if (s.kind === "message") {
    const channel = s.channel.trim();
    if (!channel) return "On Slack message";
    const from = s.fromUser.trim();
    return from ? `#${channel} from @${from}` : `#${channel}`;
  }
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
  const material = useStore((s) => s.prefs.material);
  const isGlass = material === "glass";
  const panelTransition = isGlass
    ? { duration: ENTRY_GLASS.duration, ease: ENTRY_GLASS.ease }
    : ENTRY_LINEN.spring;

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

  const isMessage = form.schedule.kind === "message";
  const valid =
    form.prompt.trim().length > 0 &&
    (!isMessage || form.schedule.channel.trim().length > 0);
  /** Message triggers act on untrusted external input. Without a sender gate,
   *  anyone who can post to the channel can drive a full-tool unattended run. */
  const unsafeAutoApprove =
    isMessage && form.auto_approve && form.schedule.fromUser.trim().length === 0;

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
          className="modal-scrim absolute inset-0 z-[60] grid place-items-center p-8"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: MODAL_BACKDROP_DURATION, ease: EASE_DECELERATE }}
          onClick={onClose}
        >
          <motion.div
            className="auto-editor glass-surface glass-radius-md w-[min(640px,calc(100vw-80px))] max-h-[calc(100vh-80px)] grid grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden"
            initial={{ opacity: 0, scale: 0.96, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 8 }}
            transition={panelTransition}
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
                <IconButton tone="faint" onClick={reset} title="Reset" aria-label="Reset">
                  <RotateCcw size={ICON.MD} strokeWidth={2} />
                </IconButton>
                <IconButton tone="faint" onClick={onClose} title="Close" aria-label="Close">
                  <X size={ICON.MD} strokeWidth={2} />
                </IconButton>
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

            {unsafeAutoApprove && (
              <div className="mx-5 mb-3 flex items-start gap-2 px-3 py-2.5 rounded-[10px] bg-warn-soft border border-warn/20">
                <TriangleAlert size={ICON.SM} strokeWidth={2} className="mt-0.5 shrink-0 text-warn" />
                <span className="text-sm text-warn leading-[1.4]">
                  Auto-Approve is on with no <strong className="font-semibold">From user</strong> gate.
                  Anyone who can post to this channel can drive a full-tool, unattended run. Set a
                  sender, or turn Auto-Approve off.
                </span>
              </div>
            )}

            {isMessage && (
              <div className="mx-5 mb-3 px-3 py-2.5 rounded-[10px] bg-surface-soft border border-line-soft">
                <span className="text-sm text-muted leading-[1.4]">
                  To search a specific repo, move this automation's channel to the target project
                  from the sidebar after it's created.
                </span>
              </div>
            )}

            {error && (
              <div className="mx-5 mb-3 grid gap-0.5 px-3 py-2.5 rounded-[10px] bg-bad-soft border border-bad/15">
                <strong className="text-bad text-sm font-semibold">Couldn't save</strong>
                <span className="text-sm text-bad leading-[1.4]">{error}</span>
              </div>
            )}

            <footer className="flex items-center justify-between gap-2 px-3 py-2.5 bg-surface-soft/40">
              <div className="flex items-center gap-2">
                <ScheduleChip
                  schedule={form.schedule}
                  onChange={(schedule) => setForm((p) => ({ ...p, schedule }))}
                />
                <div
                  className="inline-flex items-center gap-1.5 px-1 select-none cursor-pointer"
                  onClick={(e) => {
                    if ((e.target as HTMLElement).closest("button")) return;
                    setForm((p) => ({ ...p, auto_approve: !p.auto_approve }));
                  }}
                >
                  <GlassSwitch
                    size="sm"
                    checked={form.auto_approve}
                    onChange={(next) => setForm((p) => ({ ...p, auto_approve: next }))}
                    aria-label="Auto-Approve"
                  />
                  <span className="text-sm text-muted">Auto-Approve</span>
                </div>
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
  const popoverRef = useRef<HTMLDivElement>(null);
  // Anchor the portaled popover off the chip's rect. Portaling to <body>
  // lets it escape the editor modal's `overflow-hidden` and its glass
  // containing block — a glass-surface nested in another samples the
  // parent, not the page (feedback_backdrop_filter_containing_block).
  // Opens above-left: bottom edge above the chip, left edges aligned.
  const [coords, setCoords] = useState<{ bottom: number; left: number } | null>(null);

  useLayoutEffect(() => {
    if (!open || !wrapRef.current) return;
    const update = () => {
      const r = wrapRef.current!.getBoundingClientRect();
      setCoords({ bottom: window.innerHeight - r.top + 6, left: r.left });
    };
    update();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [open]);

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
          schedule.kind === "message" ? (
            <MessageSquare size={ICON.XS} strokeWidth={2} />
          ) : (
            <Clock size={ICON.XS} strokeWidth={2} />
          )
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
                zIndex: 70,
                transformOrigin: "bottom left",
              }}
              className="glass-surface surface-popover w-[340px] grid gap-3 p-3"
            >
              <GlassToggle
                size="sm"
                value={schedule.kind}
                onChange={(kind) => onChange({ ...schedule, kind: kind as ScheduleKind })}
                options={[
                  { value: "at", label: "Time" },
                  { value: "every", label: "Every" },
                  { value: "event", label: "Event" },
                  { value: "message", label: "Message" },
                ]}
              />

              <motion.div
                key={schedule.kind}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: MOTION.fast, ease: EASE_OUT }}
                className="grid gap-2.5"
              >
                {schedule.kind === "at" && (
                  <>
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
                  </>
                )}

                {schedule.kind === "every" && (
                  <>
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
                    <div className="grid grid-cols-2 gap-2">
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
                  </>
                )}

                {schedule.kind === "event" && (
                  <>
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
                      <ScheduleField label="Lead time" hint="minutes before the event">
                        <input
                          value={schedule.lead}
                          onChange={(e) => onChange({ ...schedule, lead: e.target.value })}
                          placeholder="15"
                          spellCheck={false}
                          className={schedFieldCls}
                        />
                      </ScheduleField>
                    )}
                  </>
                )}

                {schedule.kind === "message" && (
                  <>
                    <ScheduleField label="Channel" hint="Slack channel, e.g. feel-good-inc">
                      <div className="relative">
                        <Hash
                          size={ICON.XS}
                          strokeWidth={2}
                          className="absolute left-2 top-1/2 -translate-y-1/2 text-faint pointer-events-none"
                        />
                        <input
                          value={schedule.channel}
                          onChange={(e) => onChange({ ...schedule, channel: e.target.value })}
                          placeholder="channel-name"
                          spellCheck={false}
                          className={`${schedFieldCls} pl-7`}
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
                        <input
                          value={schedule.fromUser}
                          onChange={(e) => onChange({ ...schedule, fromUser: e.target.value })}
                          placeholder="username"
                          spellCheck={false}
                          className={`${schedFieldCls} pl-7`}
                        />
                      </div>
                    </ScheduleField>
                    <ScheduleField label="Keywords" hint="optional, any of — bug, error, broken">
                      <input
                        value={schedule.keywords}
                        onChange={(e) => onChange({ ...schedule, keywords: e.target.value })}
                        placeholder="bug, error"
                        spellCheck={false}
                        className={schedFieldCls}
                      />
                    </ScheduleField>
                  </>
                )}
              </motion.div>

              <div className="flex items-center gap-1.5 pt-2.5 border-t border-line-soft text-xs text-faint">
                {schedule.kind === "message" ? (
                  <MessageSquare size={ICON.XS} strokeWidth={2} />
                ) : (
                  <CalendarClock size={ICON.XS} strokeWidth={2} />
                )}
                <span className="truncate">{scheduleLabel(schedule)}</span>
              </div>
          </motion.div>
          )}
        </AnimatePresence>,
        document.body,
      )}
    </div>
  );
}

// ─── Atoms ──────────────────────────────────────────────────────────

const schedFieldCls =
  "w-full h-8 px-2 border border-line rounded-md bg-surface text-ink text-sm tabular-nums outline-none hover:border-line-strong focus:border-accent focus:shadow-[0_0_0_3px_var(--color-accent-soft)] transition-[border-color,box-shadow]";

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

