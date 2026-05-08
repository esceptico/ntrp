import { Shield } from "lucide-react";
import { useStore, type ApprovalState } from "../store";
import { respondToApproval } from "../actions";

/** First non-empty, non-diff-noise line of `text`, truncated to ~max chars.
 *  Used to render a glimpse of an approval's content (email body, file
 *  edit, etc.) inline in the banner so the user has signal without
 *  having to open the review modal for every approval. */
function snippet(text: string, max = 140): string {
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

/** Sticky banner that surfaces tool approvals above the composer. Lives
 *  outside the chat message list so it doesn't interleave with the
 *  agent's tool-call trace. Shows the next pending approval; on a
 *  decision the banner advances to the next one (or hides). */
export function ApprovalBanner() {
  const approval = useStore((s) => s.pendingApprovals[0]);
  const queueLength = useStore((s) => s.pendingApprovals.length);
  const setReviewing = useStore((s) => s.setReviewingApproval);
  if (!approval) return null;

  const { toolId, toolName, path, diff, preview } = approval;
  const hasReviewable = !!(diff || preview);
  const previewLine = approvalSnippet(approval);

  return (
    <div className="approval-banner border-b border-line-soft bg-accent-soft/30">
      <div className="mx-auto max-w-[760px] px-7 py-2 flex items-start gap-3">
        <Shield size={13} strokeWidth={1.8} className="text-accent shrink-0 mt-[3px]" />
        <div className="min-w-0 flex-1 grid gap-0.5">
          <div className="flex items-baseline gap-2 min-w-0">
            <span className="font-mono text-[12px] font-medium text-ink-soft shrink-0">
              {toolName}
            </span>
            {path && (
              <span className="font-mono text-[11.5px] text-faint truncate">{path}</span>
            )}
            {queueLength > 1 && (
              <span className="ml-auto shrink-0 text-[11px] text-faint tabular-nums">
                1 of {queueLength}
              </span>
            )}
          </div>
          {previewLine && (
            <button
              type="button"
              onClick={() => hasReviewable && setReviewing(toolId)}
              disabled={!hasReviewable}
              className="text-left text-[11.5px] text-muted truncate font-mono hover:text-ink-soft transition-colors disabled:cursor-default disabled:hover:text-muted"
              title={hasReviewable ? "Click to review full diff/preview" : undefined}
            >
              {previewLine}
            </button>
          )}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {hasReviewable && (
            <button
              type="button"
              onClick={() => setReviewing(toolId)}
              className="inline-flex items-center h-6 px-2 rounded-md text-[11.5px] text-muted hover:bg-surface-soft/60 hover:text-ink transition-colors"
            >
              Review
            </button>
          )}
          <button
            type="button"
            onClick={() => void respondToApproval(toolId, false)}
            className="inline-flex items-center h-6 px-2 rounded-md text-[11.5px] text-muted hover:bg-surface-soft/60 hover:text-ink transition-colors"
          >
            Reject
          </button>
          <button
            type="button"
            onClick={() => void respondToApproval(toolId, true)}
            className="inline-flex items-center h-6 px-2.5 rounded-md bg-ink text-on-ink text-[11.5px] font-medium hover:opacity-90 transition-opacity"
          >
            Approve
          </button>
        </div>
      </div>
    </div>
  );
}
