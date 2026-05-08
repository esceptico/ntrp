import { Check, Eye, Shield, X } from "lucide-react";
import { useStore } from "../store";
import { respondToApproval } from "../actions";

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

  return (
    <div className="approval-banner border-b border-line-soft bg-accent-soft/35">
      <div className="mx-auto max-w-[760px] px-7 py-2 flex items-center gap-3">
        <Shield size={14} strokeWidth={1.8} className="text-accent shrink-0" />
        <div className="min-w-0 flex-1 flex items-baseline gap-2">
          <span className="text-[12.5px] font-medium text-ink-soft tracking-[-0.005em] shrink-0">
            Approve
          </span>
          <span className="font-mono text-[12px] text-accent-strong shrink-0">{toolName}</span>
          {path && (
            <span className="font-mono text-[11.5px] text-faint truncate">{path}</span>
          )}
          {queueLength > 1 && (
            <span className="ml-auto shrink-0 text-[11px] text-faint tabular-nums">
              1 of {queueLength}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {hasReviewable && (
            <button
              type="button"
              onClick={() => setReviewing(toolId)}
              className="inline-flex items-center gap-1 h-7 px-2.5 rounded-md text-[12px] text-muted hover:bg-surface-soft/60 hover:text-ink transition-colors"
            >
              <Eye size={12} strokeWidth={1.8} />
              Review
            </button>
          )}
          <button
            type="button"
            onClick={() => void respondToApproval(toolId, false)}
            className="inline-flex items-center gap-1 h-7 px-2.5 rounded-md text-[12px] text-muted hover:bg-surface-soft/60 hover:text-ink transition-colors"
          >
            <X size={12} strokeWidth={2} />
            Reject
          </button>
          <button
            type="button"
            onClick={() => void respondToApproval(toolId, true)}
            className="inline-flex items-center gap-1 h-7 px-3 rounded-md bg-ink text-on-ink text-[12px] font-medium hover:opacity-90 transition-opacity"
          >
            <Check size={12} strokeWidth={2.4} />
            Approve
          </button>
        </div>
      </div>
    </div>
  );
}
