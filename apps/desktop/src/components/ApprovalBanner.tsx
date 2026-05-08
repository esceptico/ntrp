import { CornerDownLeft } from "lucide-react";
import { useStore, type ApprovalState } from "../store";
import { respondToApproval } from "../actions";

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

/** Bordered, contained approval card above the composer. Modeled after
 *  Codex's permission prompt: title + labeled fields + numbered options
 *  + Submit. Lives outside the chat trace so the agent's narrative
 *  stays clean. */
export function ApprovalBanner() {
  const approval = useStore((s) => s.pendingApprovals[0]);
  const queueLength = useStore((s) => s.pendingApprovals.length);
  const setReviewing = useStore((s) => s.setReviewingApproval);
  if (!approval) return null;

  const { toolId, toolName, path, diff, preview } = approval;
  const hasReviewable = !!(diff || preview);
  const previewLine = approvalSnippet(approval);

  return (
    <div className="px-7 pt-2 pb-3">
      <div className="mx-auto max-w-[760px] rounded-xl border border-line-soft bg-surface shadow-[var(--shadow-sm)] overflow-hidden">
        <header className="px-4 pt-3 pb-2 flex items-baseline gap-2">
          <h3 className="m-0 text-[14px] font-medium text-ink tracking-[-0.005em]">
            Approve <span className="font-mono">{toolName}</span>?
          </h3>
          {queueLength > 1 && (
            <span className="ml-auto shrink-0 text-[11px] text-faint tabular-nums">
              1 of {queueLength}
            </span>
          )}
        </header>

        {(path || previewLine) && (
          <dl className="px-4 pb-3 grid grid-cols-[max-content_minmax(0,1fr)] gap-x-6 gap-y-1 text-[12.5px]">
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

        <footer className="flex items-center gap-2 px-3 py-2 bg-surface-soft/35">
          {hasReviewable && (
            <button
              type="button"
              onClick={() => setReviewing(toolId)}
              className="inline-flex items-center h-7 px-2.5 rounded-md text-[12px] text-muted hover:bg-surface hover:text-ink transition-colors"
            >
              Review
            </button>
          )}
          <span className="ml-auto" />
          <button
            type="button"
            onClick={() => void respondToApproval(toolId, false)}
            className="inline-flex items-center h-7 px-3 rounded-md border border-line bg-surface text-[12px] text-ink-soft hover:bg-surface-soft hover:border-line-strong transition-colors"
          >
            Reject
          </button>
          <button
            type="button"
            onClick={() => void respondToApproval(toolId, true)}
            className="inline-flex items-center gap-1.5 h-7 pl-3 pr-2 rounded-md bg-ink text-on-ink text-[12px] font-medium hover:opacity-90 transition-opacity"
          >
            Approve
            <CornerDownLeft size={11} strokeWidth={2} className="opacity-70" />
          </button>
        </footer>
      </div>
    </div>
  );
}
