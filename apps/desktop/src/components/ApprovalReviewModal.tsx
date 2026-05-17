import { useRef } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";
import { Check, X } from "lucide-react";
import { useStore } from "../store";
import { respondToApproval } from "../actions";
import { SPRING_SMOOTH, modalOriginTransform } from "../lib/motion";
import { useEscapeKey } from "../lib/hooks";
import { IconButton } from "./IconButton";
import { ICON } from "../lib/icons";

const MODAL_EASE = [0.2, 0.8, 0.2, 1] as const;

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
  const liveOrigin = useStore((s) => s.modalOrigin);

  // Same snapshot pattern as PageModal — exit needs the origin that was
  // present at open time, even after the store has cleared it.
  const open = !!approval;
  const snapshotRef = useRef<{ x: number; y: number } | null>(null);
  if (open && snapshotRef.current === null && liveOrigin) {
    snapshotRef.current = liveOrigin;
  }
  if (!open && snapshotRef.current !== null) {
    snapshotRef.current = null;
  }
  const originDelta = modalOriginTransform(snapshotRef.current);

  useEscapeKey(() => close(null), !!approval);

  const root = document.querySelector("#app");
  if (!root) return null;

  return createPortal(
    <AnimatePresence>
      {open && approval && (
        <motion.div
          key="approval-review"
          className="modal-scrim absolute inset-0 z-50 grid place-items-center p-8"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18, ease: MODAL_EASE }}
          onClick={() => close(null)}
        >
          <motion.div
            className="glass-surface glass-radius-md w-[min(720px,calc(100vw-80px))] max-h-[calc(100vh-80px)] grid grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden"
            initial={
              originDelta
                ? { opacity: 0, scale: 0.94, x: originDelta.x, y: originDelta.y }
                : { opacity: 0, scale: 0.96, y: 6 }
            }
            animate={{ opacity: 1, scale: 1, x: 0, y: 0 }}
            exit={
              originDelta
                ? { opacity: 0, scale: 0.94, x: originDelta.x * 0.6, y: originDelta.y * 0.6 }
                : { opacity: 0, scale: 0.96, y: 6 }
            }
            transition={SPRING_SMOOTH}
            onClick={(e) => e.stopPropagation()}
          >
            <header className="flex items-center gap-2 px-5 pt-4 pb-3 border-b border-line-soft min-w-0">
              <span className="font-mono text-base font-medium text-ink truncate">
                {approval.toolName}
              </span>
              {approval.path && (
                <span className="font-mono text-sm text-faint truncate">{approval.path}</span>
              )}
              <IconButton
                onClick={() => close(null)}
                aria-label="Close"
                className="ml-auto shrink-0"
              >
                <X size={ICON.SM} strokeWidth={2} />
              </IconButton>
            </header>

            <div className="overflow-y-auto scroll-thin">
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
                <div className="px-5 py-6 text-sm text-faint italic">
                  No diff or preview available.
                </div>
              )}
            </div>

            <footer className="flex items-center gap-2 px-5 py-3 bg-surface-soft/40">
              <span className="text-xs text-faint font-mono">{approval.toolId.slice(0, 8)}</span>
              <button
                type="button"
                onClick={() => void respondToApproval(approval.toolId, false)}
                className="ml-auto inline-flex items-center gap-1.5 h-8 px-3 rounded-md bg-surface text-ink-soft border border-line text-sm font-medium hover:bg-surface-soft hover:border-line-strong transition-colors"
              >
                <X size={ICON.XS} strokeWidth={2} />
                Reject
              </button>
              <button
                type="button"
                onClick={() => void respondToApproval(approval.toolId, true)}
                className="inline-flex items-center gap-1.5 h-8 px-4 rounded-md bg-ink text-on-ink text-sm font-medium hover:opacity-90 transition-opacity"
              >
                <Check size={ICON.XS} strokeWidth={2.4} />
                Approve
              </button>
            </footer>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    root,
  );
}
