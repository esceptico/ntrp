import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Bot, Check, Sparkles, Zap, X } from "lucide-react";
import clsx from "clsx";
import { useStore } from "../store";
import { createSkill, type CreateAutomationPayload } from "../api";
import { fetchAutomations } from "../actions";
import { ICON } from "../lib/icons";
import { EASE_EMPHASIZED, MOTION } from "../lib/motion";

/** Shape of the JSON payload our skills (propose-automation, propose-skill)
 *  emit inside an `ntrp-proposal` fence. The fields are loose-typed (string)
 *  because the model is generating them and we want to be tolerant of
 *  whitespace / casing variations before validating on save. */
export interface AutomationProposal {
  kind: "automation";
  name: string;
  prompt: string;
  schedule: string;
  rationale: string;
}

export interface SkillProposal {
  kind: "skill";
  name: string;
  description: string;
  body: string;
  rationale: string;
}

export type Proposal = AutomationProposal | SkillProposal;

/** Parse a raw `ntrp-proposal` JSON string into a Proposal, or return null
 *  if it's malformed. Tolerant of the agent prefixing with whitespace or
 *  wrapping in additional code fences. */
export function parseProposal(raw: string): Proposal | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== "object") return null;
  const obj = parsed as Record<string, unknown>;
  const kind = obj.kind;
  if (kind === "automation") {
    if (
      typeof obj.name === "string" &&
      typeof obj.prompt === "string" &&
      typeof obj.schedule === "string" &&
      typeof obj.rationale === "string"
    ) {
      return {
        kind: "automation",
        name: obj.name,
        prompt: obj.prompt,
        schedule: obj.schedule,
        rationale: obj.rationale,
      };
    }
  } else if (kind === "skill") {
    if (
      typeof obj.name === "string" &&
      typeof obj.description === "string" &&
      typeof obj.body === "string" &&
      typeof obj.rationale === "string"
    ) {
      return {
        kind: "skill",
        name: obj.name,
        description: obj.description,
        body: obj.body,
        rationale: obj.rationale,
      };
    }
  }
  return null;
}

/** Best-effort parse of the model's free-text schedule string into the
 *  trigger fields the AutomationEditor preset expects. Anything we can't
 *  recognize falls back to "daily 09:00" — the user can adjust in the
 *  editor before saving. The user always sees the original string in the
 *  rationale block so they know what the agent proposed. */
function scheduleToTriggerFields(schedule: string): Partial<CreateAutomationPayload> {
  const s = schedule.trim().toLowerCase();
  if (!s || s === "once" || s === "manual") {
    return { trigger_type: "time", at: "09:00", days: "daily" };
  }

  // "every weekday HH:MM" / "weekdays HH:MM"
  let m = s.match(/(?:every\s+)?weekdays?\s+(\d{1,2}):(\d{2})/);
  if (m) {
    return {
      trigger_type: "time",
      at: `${m[1].padStart(2, "0")}:${m[2]}`,
      days: "weekdays",
    };
  }

  // "daily HH:MM" / "every day HH:MM"
  m = s.match(/(?:daily|every\s+day)\s+(\d{1,2}):(\d{2})/);
  if (m) {
    return {
      trigger_type: "time",
      at: `${m[1].padStart(2, "0")}:${m[2]}`,
      days: "daily",
    };
  }

  // "every N (minutes|hours|days|m|h|d)"
  m = s.match(/every\s+(\d+)\s*(minutes?|mins?|hours?|hrs?|days?|m|h|d)\b/);
  if (m) {
    const n = m[1];
    const unit = m[2][0];
    const every = unit === "m" ? `${n}m` : unit === "h" ? `${n}h` : `${n}d`;
    return { trigger_type: "time", every };
  }

  // "weekly DAY HH:MM"
  const days: Record<string, string> = {
    mon: "mon", monday: "mon",
    tue: "tue", tuesday: "tue", tues: "tue",
    wed: "wed", wednesday: "wed",
    thu: "thu", thursday: "thu", thurs: "thu",
    fri: "fri", friday: "fri",
    sat: "sat", saturday: "sat",
    sun: "sun", sunday: "sun",
  };
  m = s.match(/(?:weekly|every)\s+(mon|monday|tue|tues|tuesday|wed|wednesday|thu|thurs|thursday|fri|friday|sat|saturday|sun|sunday)\s+(\d{1,2}):(\d{2})/);
  if (m) {
    return {
      trigger_type: "time",
      at: `${m[2].padStart(2, "0")}:${m[3]}`,
      days: days[m[1]] ?? "daily",
    };
  }

  // Bare "HH:MM" — assume daily at that time.
  m = s.match(/^(\d{1,2}):(\d{2})$/);
  if (m) {
    return {
      trigger_type: "time",
      at: `${m[1].padStart(2, "0")}:${m[2]}`,
      days: "daily",
    };
  }

  return { trigger_type: "time", at: "09:00", days: "daily" };
}

/** Card rendered inline in chat where the agent emitted an `ntrp-proposal`
 *  fenced block. The agent's prose preamble appears above; this card is
 *  the structured part the user can act on.
 *
 *  Save flow:
 *  - automation → open AutomationsModal + seed editor with prefilled
 *    name/prompt/schedule. User reviews and clicks Save in the editor.
 *  - skill → POST /skills/create immediately. Skills have less to
 *    review (name/description/body) and the body's already in the
 *    rationale-style block above so the user already saw it.
 *
 *  Dismiss collapses the card visually. We don't persist the dismissal
 *  — the proposal lives in the chat history regardless, and a fresh
 *  page load reveals it again. Good enough for v1. */
export function ProposalCard({ proposal }: { proposal: Proposal }) {
  const [state, setState] = useState<"idle" | "saving" | "saved" | "dismissed" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const config = useStore((s) => s.config);
  const openAutomations = useStore((s) => s.openAutomations);
  const setAutomationEditorPreset = useStore((s) => s.setAutomationEditorPreset);

  async function onSave() {
    setState("saving");
    setError(null);
    try {
      if (proposal.kind === "automation") {
        const triggers = scheduleToTriggerFields(proposal.schedule);
        const preset: CreateAutomationPayload = {
          name: proposal.name,
          description: proposal.prompt,
          ...triggers,
        };
        setAutomationEditorPreset(preset);
        openAutomations();
        setState("saved");
      } else {
        await createSkill(config, {
          name: proposal.name,
          description: proposal.description,
          body: proposal.body,
        });
        // Refresh skill list so the new skill shows up in the command picker.
        const { refresh } = await import("../actions");
        await refresh();
        setState("saved");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setState("error");
    } finally {
      // Side-effect: an automation save also benefits from a list refresh
      // so the new entry shows up in the sidebar card if it starts running.
      if (proposal.kind === "automation") void fetchAutomations();
    }
  }

  if (state === "dismissed") return null;

  const isAutomation = proposal.kind === "automation";
  const Icon = isAutomation ? Zap : Sparkles;
  const headerLabel = isAutomation ? "Proposed automation" : "Proposed skill";

  return (
    <AnimatePresence>
      <motion.div
        layout
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 4 }}
        transition={{ duration: MOTION.panel, ease: EASE_EMPHASIZED }}
        className="my-3 rounded-xl border border-line-soft bg-surface-soft/50 p-3.5"
      >
        <div className="flex items-center gap-2 mb-2.5 text-xs font-medium uppercase tracking-[0.06em] text-faint">
          <span className="grid place-items-center w-5 h-5 rounded-md bg-accent-soft text-accent-strong">
            <Icon size={ICON.SM} strokeWidth={2} />
          </span>
          <span>{headerLabel}</span>
        </div>

        <div className="grid gap-2">
          <div className="text-base font-medium text-ink tracking-[-0.005em]">
            {proposal.name}
          </div>

          {isAutomation ? (
            <>
              <div className="text-xs text-faint">Schedule</div>
              <div className="font-mono text-sm text-ink-soft -mt-1">
                {proposal.schedule}
              </div>
              <div className="text-xs text-faint mt-1">Prompt</div>
              <div className="text-sm text-ink-soft whitespace-pre-wrap -mt-1">
                {proposal.prompt}
              </div>
            </>
          ) : (
            <>
              <div className="text-sm text-ink-soft -mt-1">
                {proposal.description}
              </div>
              <div className="text-xs text-faint mt-1">Body preview</div>
              <pre className="font-mono text-xs text-ink-soft whitespace-pre-wrap max-h-40 overflow-y-auto scroll-thin border border-line-soft rounded-md p-2 bg-bg-main/30">
                {proposal.body}
              </pre>
            </>
          )}

          <div className="flex items-start gap-1.5 mt-2 text-xs text-muted">
            <Bot size={ICON.SM} strokeWidth={1.8} className="shrink-0 mt-[2px] text-faint" />
            <span className="leading-relaxed">{proposal.rationale}</span>
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 mt-3">
          <button
            type="button"
            onClick={() => setState("dismissed")}
            disabled={state === "saving"}
            className="inline-flex items-center gap-1.5 h-7 px-3 rounded-[7px] text-xs font-medium text-muted hover:text-ink hover:bg-surface-soft transition-colors"
          >
            <X size={ICON.SM} strokeWidth={2} />
            Dismiss
          </button>
          <button
            type="button"
            onClick={() => void onSave()}
            disabled={state === "saving" || state === "saved"}
            className={clsx(
              "inline-flex items-center gap-1.5 h-7 px-3 rounded-[7px] text-xs font-medium transition-colors",
              state === "saved"
                ? "bg-ok-soft text-ok"
                : "bg-ink text-on-ink hover:opacity-90 disabled:opacity-50",
            )}
          >
            {state === "saved" ? (
              <>
                <Check size={ICON.SM} strokeWidth={2.4} />
                {isAutomation ? "Opened editor" : "Saved"}
              </>
            ) : state === "saving" ? (
              "Saving…"
            ) : (
              <>
                <Check size={ICON.SM} strokeWidth={2.2} />
                {isAutomation ? "Review & save" : "Save skill"}
              </>
            )}
          </button>
        </div>

        {error && (
          <div className="mt-2 text-xs text-bad">{error}</div>
        )}
      </motion.div>
    </AnimatePresence>
  );
}
