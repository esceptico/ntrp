import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { useStore } from "@/stores";
import { fetchSliceDetail, updateSliceAutonomy } from "@/actions/slices";
import { runAutomation } from "@/actions/automations";
import { createSessionWithSlice, switchSession } from "@/actions/sessions";
import { sendMessage } from "@/actions/messages";
import { Play } from "lucide-react";
import { ICON } from "@/lib/icons";
import { AskCard } from "@/features/slices/components/AskCard";
import { OpenLoops } from "@/features/slices/components/OpenLoops";
import { SliceActivity } from "@/features/slices/components/SliceActivity";
import { ChargeButton } from "@/components/ui/ChargeButton";
import { formatRelativePast } from "@/lib/format";
import { RISE_IN, RISE_SETTLED, MOTION, EASE_DECELERATE } from "@/lib/tokens/motion";

/** Slice room: the full-screen detail view for one slice, opened from the
 *  Home slices strip / focus rows / related chips (`openSlice(key)` — same
 *  store-mediated slot Task 10 wired for Home vs Chat). Renders in App.tsx
 *  wherever `openSliceKey` is set, ahead of the Home/Chat branch.
 *
 *  Layout: back link → title + autonomy control → last-activity line →
 *  top ask's AskCard → OpenLoops → SliceActivity → RELATED chips → a
 *  scoped composer that provisions a slice-tagged session on first send. */
export function SliceRoom({ sliceKey }: { sliceKey: string }) {
  const detail = useStore((s) => s.slices.detailByKey[sliceKey]);
  const overviewSlices = useStore((s) => s.slices.overview?.slices);
  const openSlice = useStore((s) => s.openSlice);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);

  useEffect(() => {
    void fetchSliceDetail(sliceKey);
  }, [sliceKey]);

  if (!detail) {
    return (
      <div className="mx-auto grid w-[640px] max-w-full gap-6 px-4 pt-[12vh]">
        <button
          type="button"
          onClick={() => openSlice(null)}
          className="justify-self-start text-sm text-faint hover:text-ink-soft"
        >
          ← Home
        </button>
        <p className="text-sm text-faint">Loading…</p>
      </div>
    );
  }

  const topAsk = detail.asks[0] ?? null;
  const relatedTitle = (key: string) => overviewSlices?.find((s) => s.key === key)?.title ?? key;

  // Header status line, best data first: agent running now > the agent's
  // last run (first line of its report + when) > never-ran. The line is the
  // door to the agent's channel (its full transcript); Run now sits beside
  // it. The channel session itself is excluded from ACTIVITY — that list is
  // the user's own chats, not infrastructure.
  const agentAuto = detail.automations.find(
    (
      a,
    ): a is {
      name: string;
      task_id?: string;
      thread_id?: string | null;
      last_result?: string | null;
      last_run_at?: string | null;
      running_since?: string | null;
    } => typeof a === "object" && a !== null && (a as { name?: string }).name === `slice:${sliceKey}`,
  );
  const agentRunning = Boolean(agentAuto?.running_since);
  const agentSummary = agentAuto?.last_result?.split("\n")[0]?.trim();
  const agentLine = agentRunning
    ? "Agent working now…"
    : agentSummary && agentAuto?.last_run_at
      ? `Agent, ${formatRelativePast(agentAuto.last_run_at)} ago — ${agentSummary}`
      : agentAuto?.last_run_at
        ? `Agent ran ${formatRelativePast(agentAuto.last_run_at)} ago`
        : "Agent hasn’t run yet";
  const agentChannelId = agentAuto?.thread_id ?? null;
  const userSessions = detail.sessions.filter((s) => s.session_id !== agentChannelId);

  const isEmpty =
    detail.open_loops.length === 0 && detail.asks.length === 0 && userSessions.length === 0;

  const runAgentNow = async () => {
    if (!agentAuto?.task_id) return;
    try {
      await runAutomation(agentAuto.task_id);
      await fetchSliceDetail(sliceKey);
    } catch {
      useStore.getState().pushToast({
        id: `slice-run-fail:${sliceKey}`,
        title: "Couldn’t start the agent",
        status: "failed",
        target: { kind: "automation" },
      });
    }
  };

  const discussAsk = (ask: { text: string }) => {
    setDraft(`About "${ask.text}" — `);
    document.getElementById("slice-composer-input")?.focus();
  };

  const grantAct = async () => {
    try {
      await updateSliceAutonomy(sliceKey, "act");
    } catch {
      useStore.getState().pushToast({
        id: `slice-autonomy-fail:${sliceKey}`,
        title: "Couldn’t grant act autonomy",
        status: "failed",
        target: { kind: "automation" },
      });
      await fetchSliceDetail(sliceKey);
    }
  };

  const revokeAct = async () => {
    try {
      await updateSliceAutonomy(sliceKey, "observe");
    } catch {
      useStore.getState().pushToast({
        id: `slice-autonomy-fail:${sliceKey}`,
        title: "Couldn’t revoke act autonomy",
        status: "failed",
        target: { kind: "automation" },
      });
      await fetchSliceDetail(sliceKey);
    }
  };

  const send = async () => {
    const text = draft.trim();
    if (!text || sending) return;
    setSending(true);
    setDraft("");
    try {
      await createSessionWithSlice(sliceKey);
      await sendMessage(text);
    } catch {
      setDraft(text);
      useStore.getState().pushToast({
        id: `slice-send-fail:${sliceKey}`,
        title: "Couldn’t send message",
        status: "failed",
        target: { kind: "automation" },
      });
    } finally {
      setSending(false);
    }
  };

  return (
    <motion.div
      initial={RISE_IN}
      animate={RISE_SETTLED}
      transition={{ duration: MOTION.trace, ease: EASE_DECELERATE }}
      className="flex h-full min-h-0 flex-col"
    >
      {/* Content scrolls; the scoped composer stays pinned below it.
          overflow-x-hidden is the structural backstop: a child that loses
          its min-w-0 again clips at the pane instead of pushing the whole
          layout off-screen. */}
      <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden">
        <div className="mx-auto grid w-[640px] max-w-full gap-6 px-4 pt-14 pb-8">
      <button
        type="button"
        onClick={() => openSlice(null)}
        className="justify-self-start text-sm text-faint hover:text-ink-soft"
      >
        ← Home
      </button>

      <div className="grid gap-1.5">
        {/* Autonomy control sits beside the title as a quiet chip (mock:
            "asks before acting" inline with the name), not parked at the
            far edge. Grant keeps the hold-to-arm ceremony; revoke is a
            plain click — de-escalation needs none. */}
        <div className="flex min-w-0 items-center gap-3">
          <h1 className="m-0 min-w-0 truncate text-2xl font-medium tracking-[-0.015em] text-ink">
            {detail.title}
          </h1>
          {detail.autonomy === "observe" ? (
            <span
              title="Autonomy contract: the agent reads this slice and updates its page, but takes no external action. Hold to grant it the right to act (run automations and workflows — irreversible steps still need your approval)."
            >
              <ChargeButton
                key={detail.autonomy}
                label="Observe only"
                armedLabel="Act granted"
                onArmed={() => void grantAct()}
              />
            </span>
          ) : (
            <button
              type="button"
              onClick={() => void revokeAct()}
              title="Click to revoke act autonomy"
              className="shrink-0 rounded-md bg-ink px-2.5 py-1 text-xs font-medium text-on-ink hover:opacity-90"
            >
              Acting
            </button>
          )}
        </div>
        <div className="flex min-w-0 items-center gap-2">
          {agentChannelId ? (
            <button
              type="button"
              onClick={() => void switchSession(agentChannelId)}
              title="Open the agent’s channel — every run’s full transcript"
              className="flex min-w-0 items-center gap-1.5 text-left text-xs text-faint hover:text-ink-soft"
            >
              {agentRunning && (
                <span aria-hidden className="size-1.5 shrink-0 animate-pulse rounded-full bg-ink" />
              )}
              <span className="min-w-0 truncate underline decoration-line-soft underline-offset-2">
                {agentLine}
              </span>
            </button>
          ) : (
            <p className="m-0 min-w-0 truncate text-xs text-faint">{agentLine}</p>
          )}
          {agentAuto?.task_id && !agentRunning && (
            <button
              type="button"
              onClick={() => void runAgentNow()}
              className="flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-2xs font-medium text-muted hover:bg-surface-soft hover:text-ink"
            >
              <Play size={ICON.XS} strokeWidth={2} />
              Run now
            </button>
          )}
        </div>
      </div>

      {topAsk && (
        <AnimatePresence initial={false}>
          <AskCard key={topAsk.id} ask={topAsk} onDiscuss={discussAsk} />
        </AnimatePresence>
      )}

      {isEmpty && (
        <p className="m-0 text-sm text-faint">
          Nothing on file yet — message the slice below, or its agent will report after its next run.
        </p>
      )}

      <OpenLoops
        loops={detail.open_loops}
        onDiscuss={(loop) => {
          setDraft(`About the open loop "${loop}" — `);
          document.getElementById("slice-composer-input")?.focus();
        }}
      />
      <SliceActivity sessions={userSessions} />

      {detail.related.length > 0 && (
        <div className="grid gap-2">
          <span className="text-2xs font-semibold tracking-wide text-faint uppercase">Related</span>
          <div className="flex flex-wrap gap-1.5">
            {detail.related.map((key) => (
              <button
                key={key}
                type="button"
                onClick={() => openSlice(key)}
                className="rounded-full bg-surface-soft px-2.5 py-1 text-xs text-ink-soft hover:text-ink"
              >
                {relatedTitle(key)}
              </button>
            ))}
          </div>
        </div>
      )}

        </div>
      </div>

      <div className="mx-auto w-[640px] max-w-full shrink-0 px-4 pb-6">
        <div className="flex h-[52px] w-full items-center gap-2 rounded-[13px] border border-line bg-surface-2 px-4 shadow-md">
          <input
            id="slice-composer-input"
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
            placeholder={`Message in ${detail.title}…`}
            disabled={sending}
            className="min-w-0 flex-1 bg-transparent text-sm text-ink placeholder:text-faint focus:outline-none disabled:opacity-60"
          />
        </div>
      </div>
    </motion.div>
  );
}
