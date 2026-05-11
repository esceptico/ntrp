import { useEffect } from "react";
import { CornerDownLeft } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { useStore, type ApprovalState } from "../store";
import { respondToAllApprovals, respondToApproval } from "../actions";
import { ICON } from "../lib/icons";

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

/** Legacy single-line fallback used when the preview isn't structured
 *  (i.e. no `Key: value` rows). Keeps the old compact rendering for tools
 *  like bash that just pass a one-liner. */
function approvalSnippet(approval: ApprovalState): string {
  if (approval.preview) return snippet(approval.preview);
  if (approval.diff) return snippet(approval.diff);
  return "";
}

/** Detect a "structured preview" the backend wrote as `Key: value` rows
 *  optionally followed by a free-text body (separated by a blank line).
 *  Used by create_automation / create_skill so the approval card can
 *  render headers + a prominent body section rather than a single
 *  truncated line. */
interface StructuredPreview {
  fields: { key: string; value: string }[];
  body: { label: string; text: string } | null;
}

function parseStructuredPreview(text: string): StructuredPreview | null {
  if (!text) return null;
  const lines = text.split("\n");
  const fields: { key: string; value: string }[] = [];
  let cursor = 0;
  // Accumulate leading `Key: value` lines. Stop on a blank line, which
  // separates the field block from any body that follows.
  while (cursor < lines.length) {
    const line = lines[cursor];
    if (!line.trim()) break;
    const m = line.match(/^([A-Z][A-Za-z _-]{0,30}):\s*(.*)$/);
    if (!m) break;
    fields.push({ key: m[1].trim(), value: m[2].trim() });
    cursor++;
  }
  if (fields.length === 0) return null;
  // Skip the blank separator(s) and look for an optional body — a
  // single label line ("Prompt:" / "Body:" / ...) followed by the
  // remaining content as one block.
  while (cursor < lines.length && !lines[cursor].trim()) cursor++;
  let body: StructuredPreview["body"] = null;
  if (cursor < lines.length) {
    const labelMatch = lines[cursor].match(/^([A-Z][A-Za-z _-]{0,30}):\s*$/);
    if (labelMatch && cursor + 1 < lines.length) {
      body = { label: labelMatch[1], text: lines.slice(cursor + 1).join("\n").trim() };
    } else {
      // No label — treat everything that's left as a generic body.
      body = { label: "Detail", text: lines.slice(cursor).join("\n").trim() };
    }
  }
  return { fields, body };
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
  // Hide the banner deck entirely while the Review modal is open. The
  // modal carries the same toolName + full preview/diff, so showing the
  // banner stack behind it just creates a confusing double-surface (and
  // historically clashed with the modal's z-index, since each banner
  // card uses inline z-index up to 100 while the modal sits at z-50).
  if (reviewingId) return null;

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

/** One row inside the rich approval card. The value is monospace because
 *  almost every field that lands here is a path, an interval, a name, a
 *  schedule label — all things where character alignment helps reading. */
function FieldRow({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="text-faint">{label}</dt>
      <dd className="m-0 font-mono text-ink-soft break-words">{value}</dd>
    </>
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
  const structured = preview ? parseStructuredPreview(preview) : null;
  const previewLine = !structured ? approvalSnippet(approval) : "";
  // Diff opens the modal. So does a structured preview with a long body
  // — keeps the card compact while still letting the user see the full
  // content via Review.
  const longBody = structured?.body && structured.body.text.length > 480;
  const hasReviewable = !!(diff || longBody);
  const showBulk = isFront && totalPending > 1;

  return (
    <div
      aria-hidden={!interactive || undefined}
      className="rounded-xl border border-line-soft bg-surface shadow-[var(--shadow-sm)] overflow-hidden"
    >
      <header className="px-4 pt-3 pb-2 flex items-baseline gap-2">
        <h3 className="m-0 text-md font-medium text-ink tracking-[-0.005em]">
          {structured
            ? "Approve action"
            : <>Approve <span className="font-mono">{toolName}</span>?</>}
        </h3>
        {showBulk && (
          <span className="ml-auto shrink-0 text-xs text-faint tabular-nums">
            1 of {totalPending}
          </span>
        )}
      </header>

      {structured ? (
        // Rich path: render Key/Value fields as a definition list, plus
        // an optional body section (the automation prompt or skill
        // body) below. Body is clamped to ~6 lines on the card; Review
        // opens the full content.
        <div className="px-4 pb-3 grid gap-2.5">
          <div className="text-xs font-mono text-faint">{toolName}</div>
          <dl className="grid grid-cols-[max-content_minmax(0,1fr)] gap-x-5 gap-y-1 text-sm">
            {structured.fields.map((f) => (
              <FieldRow key={f.key} label={f.key} value={f.value} />
            ))}
          </dl>
          {structured.body && structured.body.text && (
            <div className="grid gap-1">
              <div className="text-xs font-medium uppercase tracking-[0.06em] text-faint">
                {structured.body.label}
              </div>
              <pre
                className="m-0 font-mono text-xs text-ink-soft whitespace-pre-wrap break-words rounded-md border border-line-soft bg-bg-main/30 p-2 max-h-[8.4em] overflow-hidden"
              >
                {structured.body.text}
              </pre>
            </div>
          )}
        </div>
      ) : (
        (path || previewLine) && (
          <dl className="px-4 pb-3 grid grid-cols-[max-content_minmax(0,1fr)] gap-x-6 gap-y-1 text-sm">
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
        )
      )}

      <footer className="flex flex-wrap items-center gap-2 px-3 py-2 bg-surface-soft/35">
        {hasReviewable && (
          <button
            type="button"
            tabIndex={interactive ? 0 : -1}
            onClick={() => setReviewing(toolId)}
            className="inline-flex items-center h-7 px-2.5 rounded-md text-sm text-muted hover:bg-surface hover:text-ink transition-colors"
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
              className="inline-flex items-center h-7 px-2.5 rounded-md text-sm text-muted hover:bg-surface hover:text-ink transition-colors"
            >
              Reject all
            </button>
            <button
              type="button"
              tabIndex={interactive ? 0 : -1}
              onClick={() => void respondToAllApprovals(true)}
              className="inline-flex items-center h-7 px-3 rounded-md border border-line bg-surface text-sm text-ink-soft hover:bg-surface-soft hover:border-line-strong transition-colors"
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
          className="inline-flex items-center h-7 px-3 rounded-md border border-line bg-surface text-sm text-ink-soft hover:bg-surface-soft hover:border-line-strong transition-colors"
        >
          Reject
        </button>
        <button
          type="button"
          tabIndex={interactive ? 0 : -1}
          onClick={() => void respondToApproval(toolId, true)}
          title="Approve (⌘↩)"
          className="inline-flex items-center gap-1.5 h-7 pl-3 pr-2 rounded-md bg-ink text-on-ink text-sm font-medium hover:opacity-90 transition-opacity"
        >
          Approve
          <span className="inline-flex items-center gap-0.5 opacity-70 text-2xs font-mono leading-none">
            ⌘
            <CornerDownLeft size={ICON.XS} strokeWidth={2.2} />
          </span>
        </button>
      </footer>
    </div>
  );
}
