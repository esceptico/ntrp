import { Check, X } from "lucide-react";
import { useStore } from "@/stores";
import { respondToApproval } from "@/actions";
import { IconButton } from "@/components/ui/IconButton";
import { Button } from "@/components/ui/Button";
import { PageModal } from "@/components/ui/PageModal";
import { ICON } from "@/lib/icons";
import { ScrollFadeTop } from "@/components/ui/ScrollBlur";

const DIFF_LINE = "block px-2 min-w-max";
const DIFF_ADD = "bg-[rgba(79,138,58,0.10)] text-[#2e6620] dark:bg-[rgba(135,154,57,0.16)] dark:text-[#afc463]";
const DIFF_DEL = "bg-[rgba(184,68,43,0.10)] text-[#8a3220] dark:bg-[rgba(209,77,65,0.16)] dark:text-[#e58075]";
const DIFF_HUNK = "text-info";

function diffClassFor(line: string): string {
  if (line.startsWith("+++") || line.startsWith("---") || line.startsWith("@@")) {
    return `${DIFF_LINE} ${DIFF_HUNK}`;
  }
  if (line.startsWith("+")) return `${DIFF_LINE} ${DIFF_ADD}`;
  if (line.startsWith("-")) return `${DIFF_LINE} ${DIFF_DEL}`;
  return DIFF_LINE;
}

/** Diff/preview review for a pending approval. Opens when the banner's
 *  Review button is clicked. Approve/Reject actions live here too so the
 *  user doesn't have to dismiss the modal first. */
export function ApprovalReviewModal() {
  const reviewing = useStore((s) => s.reviewingApprovalToolId);
  const approval = useStore((s) =>
    reviewing ? s.pendingApprovals.find((a) => a.toolId === reviewing) ?? null : null,
  );
  const close = useStore((s) => s.setReviewingApproval);
  const origin = useStore((s) => s.modalOrigin);

  return (
    <PageModal
      open={!!approval}
      onClose={() => close(null)}
      origin={origin}
      size="w-[min(720px,calc(100vw-80px))] max-h-[calc(100vh-80px)]"
      grid="grid-rows-[auto_minmax(0,1fr)_auto]"
      ariaLabel={approval ? `Review ${approval.toolName}` : "Review approval"}
    >
      {approval && (
        <>
          <header className="flex items-center gap-2 px-5 pt-4 pb-3 min-w-0">
            <span className="font-mono text-base font-medium text-ink truncate">
              {approval.toolName}
            </span>
            {approval.path && (
              <span className="font-mono text-sm text-faint truncate">{approval.path}</span>
            )}
            <IconButton onClick={() => close(null)} aria-label="Close" className="ml-auto shrink-0">
              <X size={ICON.SM} strokeWidth={2} />
            </IconButton>
          </header>

          <div className="overflow-y-auto scroll-thin">
            <ScrollFadeTop />
            {approval.diff ? (
              <div className="font-mono text-xs leading-[1.5] whitespace-pre overflow-x-auto overflow-y-auto max-h-60 scroll-thin">
                <div>
                  {approval.diff.split("\n").map((line, i) => (
                    <span key={i} className={diffClassFor(line)}>
                      {line || " "}
                    </span>
                  ))}
                </div>
              </div>
            ) : approval.preview ? (
              <pre className="m-0 px-5 py-4 font-mono text-sm leading-[1.55] text-ink-soft whitespace-pre-wrap">
                {approval.preview}
              </pre>
            ) : (
              <div className="px-5 py-6 text-sm text-muted italic">
                No diff or preview available.
              </div>
            )}
          </div>

          <footer className="flex items-center gap-2 px-5 py-3 bg-surface-soft/40">
            <span className="text-xs text-faint font-mono">{approval.toolId.slice(0, 8)}</span>
            <Button
              variant="secondary"
              leadingIcon={X}
              onClick={() => void respondToApproval(approval.toolId, false)}
              className="ml-auto"
            >
              Reject
            </Button>
            <Button
              variant="primary"
              leadingIcon={Check}
              onClick={() => void respondToApproval(approval.toolId, true)}
            >
              Approve
            </Button>
          </footer>
        </>
      )}
    </PageModal>
  );
}
