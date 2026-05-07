import { memo } from "react";
import { Check, Shield, X } from "lucide-react";
import clsx from "clsx";
import { useStore } from "../store";
import { respondToApproval } from "../actions";

function diffClassFor(line: string): string {
  if (line.startsWith("+++") || line.startsWith("---") || line.startsWith("@@")) {
    return "diff-line diff-hunk";
  }
  if (line.startsWith("+")) return "diff-line diff-add";
  if (line.startsWith("-")) return "diff-line diff-del";
  return "diff-line";
}

export const ApprovalCard = memo(function ApprovalCard({ id }: { id: string }) {
  const message = useStore((s) => s.messages.get(id));
  const approval = message?.approval;
  if (!approval) return null;

  const { toolId, toolName, path, preview, status } = approval;
  const pending = status === "pending";

  return (
    <article className="grid grid-cols-[minmax(0,1fr)] my-1 animate-roll-in" data-id={id}>
      <div
        className={clsx(
          "rounded-[12px] border bg-surface overflow-hidden",
          pending ? "border-accent/40" : "border-line",
        )}
      >
        <header className="flex items-center gap-2 px-3 py-2 bg-surface-soft/60">
          <Shield
            size={13}
            strokeWidth={1.8}
            className={clsx(pending ? "text-accent" : "text-faint")}
          />
          <span className="font-mono text-[12px] font-medium text-ink-soft">{toolName}</span>
          {path && <span className="font-mono text-[11.5px] text-faint truncate">{path}</span>}
          <span className="ml-auto text-[10.5px] uppercase tracking-[0.08em] font-medium">
            {pending && <span className="text-accent">Approval needed</span>}
            {status === "approved" && <span className="text-ok">Approved</span>}
            {status === "rejected" && <span className="text-bad">Rejected</span>}
          </span>
        </header>

        {approval.diff && (
          <div className="diff-preview scroll-thin border-b border-line-soft">
            <div>
              {approval.diff.split("\n").map((line, i) => (
                <span key={i} className={diffClassFor(line)}>
                  {line || " "}
                </span>
              ))}
            </div>
          </div>
        )}

        {!approval.diff && preview && (
          <pre className="m-0 px-3 py-2 font-mono text-[11.5px] leading-[1.5] text-ink-soft whitespace-pre-wrap max-h-[180px] overflow-auto scroll-thin">
            {preview}
          </pre>
        )}

        {pending && (
          <div className="flex items-center gap-2 px-3 py-2">
            <button
              type="button"
              onClick={() => void respondToApproval(id, toolId, true)}
              className="inline-flex items-center gap-1.5 h-7 px-3 rounded-md bg-ink text-on-ink text-[12px] font-medium hover:opacity-90 transition-opacity"
            >
              <Check size={12} strokeWidth={2.4} />
              Approve
            </button>
            <button
              type="button"
              onClick={() => void respondToApproval(id, toolId, false)}
              className="inline-flex items-center gap-1.5 h-7 px-3 rounded-md bg-surface text-ink-soft border border-line text-[12px] font-medium hover:bg-surface-soft hover:border-line-strong transition-colors"
            >
              <X size={12} strokeWidth={2} />
              Reject
            </button>
            <span className="ml-auto text-[11px] text-faint">
              {toolId.slice(0, 8)}
            </span>
          </div>
        )}
      </div>
    </article>
  );
});
