import { useEffect } from "react";
import { CornerDownLeft } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { useStore, type ApprovalState } from "../store";
import { respondToAllApprovals, respondToApproval } from "../actions";

// Spring physics — tuned to feel like iOS 17 / Linear / Raycast: the
// card moves with mass + damping, not a tween. Stiffness ~340 gives a
// quick settle; damping 32 kills overshoot so it doesn't feel bouncy
// (we're not animating a Slack message, just a card dismissing).
const SPRING = { type: "spring", stiffness: 340, damping: 32, mass: 0.9 } as const;

const STACK_OPACITY = [1, 0.55, 0.3];
const STACK_Y = [0, -6, -12];
const STACK_SCALE_STEP = 0.035;

/** First non-empty, non-diff-noise line of `text`, truncated to ~max chars. */
function snippet(text: string, max = 160): string {
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    if (line.startsWith("---") || line.startsWith("+++") || line.startsWith("@@")) continue;
    return line.length <= max ? line : line.slice(0, max).trimEnd() + "…";
  }
  return "";
}

function approvalSnippet(approval: ApprovalState): string {
  if (approval.preview) return snippet(approval.preview);
  if (approval.diff) return snippet(approval.diff);
  return "";
}

/** Card-deck stack of approvals. Front card is full-size + interactive,
 *  up to two behind cards peek out as smaller, dimmer slivers above.
 *  Beyond that, count rolls into the front card's bulk actions. */
export function ApprovalBanner() {
  const approvals = useStore((s) => s.pendingApprovals);
  const reviewingId = useStore((s) => s.reviewingApprovalToolId);

  // Cmd/Ctrl+Enter approves the front card from anywhere — including
  // when the composer is focused. Plain Enter in the composer is
  // reserved for sending a message (which routes to "reject all with
  // this text as feedback" when approvals are pending). Skip when the
  // Review modal is open.
  useEffect(() => {
    if (approvals.length === 0) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Enter") return;
      if (!(e.metaKey || e.ctrlKey)) return;
      if (e.altKey || e.shiftKey) return;
      if (reviewingId) return;
      e.preventDefault();
      e.stopPropagation();
      void respondToApproval(approvals[0].toolId, true);
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [approvals, reviewingId]);

  if (approvals.length === 0) return null;

  return (
    <div className="px-7 pt-2 pb-3">
      <div className="mx-auto max-w-[760px]">
        {/* grid + grid-area="stack" makes every child share one cell —
            the container sizes to the largest child (the front card)
            and every card overlaps in the same space. Only the front
            is interactive; back cards are decorative slivers. */}
        <div
          className="grid"
          style={{ gridTemplateAreas: '"stack"', paddingTop: approvals.length > 1 ? 14 : 0 }}
        >
          <AnimatePresence initial={false}>
            {approvals.map((approval, index) => {
              const visible = index < STACK_OPACITY.length;
              return (
                <motion.div
                  key={approval.toolId}
                  style={{
                    gridArea: "stack",
                    zIndex: 100 - index,
                    pointerEvents: index === 0 ? "auto" : "none",
                  }}
                  initial={{ opacity: 0, scale: 0.97, y: 8 }}
                  animate={{
                    opacity: visible ? STACK_OPACITY[index] : 0,
                    scale: 1 - index * STACK_SCALE_STEP,
                    y: visible ? STACK_Y[index] : STACK_Y[STACK_OPACITY.length - 1],
                  }}
                  exit={{ opacity: 0, scale: 0.96, y: 4 }}
                  transition={SPRING}
                >
                  <ApprovalCard
                    approval={approval}
                    interactive={index === 0}
                    totalPending={approvals.length}
                    isFront={index === 0}
                  />
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}

function ApprovalCard({
  approval,
  interactive,
  isFront,
  totalPending,
}: {
  approval: ApprovalState;
  interactive: boolean;
  isFront: boolean;
  totalPending: number;
}) {
  const setReviewing = useStore((s) => s.setReviewingApproval);
  const { toolId, toolName, path, diff, preview } = approval;
  const hasReviewable = !!(diff || preview);
  const previewLine = approvalSnippet(approval);
  const showBulk = isFront && totalPending > 1;

  return (
    <div
      aria-hidden={!interactive || undefined}
      className="rounded-xl border border-line-soft bg-surface shadow-[var(--shadow-sm)] overflow-hidden"
    >
      <header className="px-4 pt-3 pb-2 flex items-baseline gap-2">
        <h3 className="m-0 text-[14.5px] font-medium text-ink tracking-[-0.005em]">
          Approve <span className="font-mono">{toolName}</span>?
        </h3>
        {showBulk && (
          <span className="ml-auto shrink-0 text-[11.5px] text-faint tabular-nums">
            1 of {totalPending}
          </span>
        )}
      </header>

      {(path || previewLine) && (
        <dl className="px-4 pb-3 grid grid-cols-[max-content_minmax(0,1fr)] gap-x-6 gap-y-1 text-[13px]">
          {path && (
            <>
              <dt className="text-faint">Target</dt>
              <dd className="m-0 font-mono text-ink-soft truncate">{path}</dd>
            </>
          )}
          {previewLine && (
            <>
              <dt className="text-faint">Content</dt>
              <dd className="m-0 font-mono text-ink-soft truncate">{previewLine}</dd>
            </>
          )}
        </dl>
      )}

      <footer className="flex flex-wrap items-center gap-2 px-3 py-2 bg-surface-soft/35">
        {hasReviewable && (
          <button
            type="button"
            tabIndex={interactive ? 0 : -1}
            onClick={() => setReviewing(toolId)}
            className="inline-flex items-center h-7 px-2.5 rounded-md text-[12.5px] text-muted hover:bg-surface hover:text-ink transition-colors"
          >
            Review
          </button>
        )}
        <span className="ml-auto" />
        {showBulk && (
          <>
            <button
              type="button"
              tabIndex={interactive ? 0 : -1}
              onClick={() => void respondToAllApprovals(false)}
              className="inline-flex items-center h-7 px-2.5 rounded-md text-[12.5px] text-muted hover:bg-surface hover:text-ink transition-colors"
            >
              Reject all
            </button>
            <button
              type="button"
              tabIndex={interactive ? 0 : -1}
              onClick={() => void respondToAllApprovals(true)}
              className="inline-flex items-center h-7 px-3 rounded-md border border-line bg-surface text-[12.5px] text-ink-soft hover:bg-surface-soft hover:border-line-strong transition-colors"
            >
              Approve all
            </button>
            <span className="w-px h-5 bg-line-soft mx-0.5" aria-hidden />
          </>
        )}
        <button
          type="button"
          tabIndex={interactive ? 0 : -1}
          onClick={() => void respondToApproval(toolId, false)}
          className="inline-flex items-center h-7 px-3 rounded-md border border-line bg-surface text-[12.5px] text-ink-soft hover:bg-surface-soft hover:border-line-strong transition-colors"
        >
          Reject
        </button>
        <button
          type="button"
          tabIndex={interactive ? 0 : -1}
          onClick={() => void respondToApproval(toolId, true)}
          title="Approve (⌘↩)"
          className="inline-flex items-center gap-1.5 h-7 pl-3 pr-2 rounded-md bg-ink text-on-ink text-[12.5px] font-medium hover:opacity-90 transition-opacity"
        >
          Approve
          <span className="inline-flex items-center gap-0.5 opacity-70 text-[11px] font-mono leading-none">
            ⌘
            <CornerDownLeft size={10} strokeWidth={2.2} />
          </span>
        </button>
      </footer>
    </div>
  );
}
