import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { useStore } from "@/stores";
import { fetchSliceDetail, updateSliceAutonomy } from "@/actions/slices";
import { createSessionWithSlice } from "@/actions/sessions";
import { sendMessage } from "@/actions/messages";
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

  // Header status line, best data first: the slice agent's last run (first
  // line of its result + when), else the page's own updated date.
  const agentAuto = detail.automations.find(
    (a): a is { name: string; last_result?: string | null; last_run_at?: string | null } =>
      typeof a === "object" && a !== null && (a as { name?: string }).name === `slice:${sliceKey}`,
  );
  const agentSummary = agentAuto?.last_result?.split("\n")[0]?.trim();
  const agentLine =
    agentSummary && agentAuto?.last_run_at
      ? `Agent, ${formatRelativePast(agentAuto.last_run_at)} ago — ${agentSummary}`
      : `Last activity ${formatRelativePast(detail.updated)} ago`;

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
      {/* Content scrolls; the scoped composer stays pinned below it. */}
      <div className="min-h-0 flex-1 overflow-y-auto">
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
          <h1 className="m-0 min-w-0 truncate text-[22px] font-medium tracking-[-0.01em] text-ink">
            {detail.title}
          </h1>
          {detail.autonomy === "observe" ? (
            <ChargeButton
              key={detail.autonomy}
              label="Observe only"
              armedLabel="Act granted"
              onArmed={() => void grantAct()}
            />
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
        <p className="m-0 min-w-0 truncate text-xs text-faint">{agentLine}</p>
      </div>

      {topAsk && (
        <AnimatePresence initial={false}>
          <AskCard key={topAsk.id} ask={topAsk} onDiscuss={discussAsk} />
        </AnimatePresence>
      )}

      <OpenLoops loops={detail.open_loops} />
      <SliceActivity sessions={detail.sessions} automations={detail.automations} />

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
