import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { motion } from "motion/react";
import { Check, GitFork, Pencil, X } from "lucide-react";
import type { PageEditKind, RenderedClaim } from "../../api/memoryItems";
import { SPRING_CARD, SPRING_LAYOUT } from "../../lib/tokens/motion";
import { ICON } from "../../lib/icons";
import { Badge } from "../Badge";
import { feedbackTone, provenanceLabel, provenanceTone } from "./lens";

export type ClaimOpKind = Extract<PageEditKind, "edit" | "reject" | "accept">;
export interface ClaimOp {
  kind: ClaimOpKind;
  claim_id: string;
  new_text?: string;
}

/** One claim-backed line in a lens page. At rest it's prose with a faint
 *  accent gutter on hover; clicking lifts it into an inline editor offering
 *  Edit (supersede with new text), Supersede (explicit successor), Accept
 *  (confirm), and Remove-from-lens (reject). The claim survives every op —
 *  never-delete. The editor is a sibling-elevated card (glass drop shadow),
 *  not a modal, so it samples the page surface, not the slab. */
export function ClaimBlock({
  block,
  editing,
  busy,
  exiting,
  onOpen,
  onClose,
  onCommit,
  onPeek,
}: {
  block: RenderedClaim;
  editing: boolean;
  busy: boolean;
  /** "supersede" = old line collapses out as successor takes its place;
   *  "reject" = leaves left. Drives the direction-encoded exit. */
  exiting: "supersede" | "reject" | null;
  onOpen: () => void;
  onClose: () => void;
  onCommit: (op: ClaimOp) => void;
  /** Peel into the claim detail (provenance / lenses). */
  onPeek: () => void;
}) {
  const exitVariant = exiting === "reject" ? { opacity: 0, x: -24, height: 0, marginBottom: 0 } : { opacity: 0, height: 0, marginBottom: 0 };

  return (
    <motion.div
      layout
      initial={false}
      exit={exitVariant}
      transition={{ layout: SPRING_LAYOUT, default: SPRING_CARD }}
      className="relative"
    >
      {editing ? (
        <ClaimEditor block={block} busy={busy} onClose={onClose} onCommit={onCommit} />
      ) : (
        <button
          type="button"
          onClick={onOpen}
          className="group/claim relative block w-full pl-4 pr-2 py-1.5 text-left text-sm leading-[1.55] text-ink-soft rounded-md transition-colors hover:bg-surface-soft/60"
        >
          {/* gutter rule — light catches the wet edge of the backing claim */}
          <span
            aria-hidden
            className="absolute left-1 top-1.5 bottom-1.5 w-px rounded-full bg-accent/0 transition-colors duration-150 group-hover/claim:bg-accent/50"
          />
          <span className={block.feedback === "corrected" ? "text-faint line-through decoration-line" : undefined}>
            {block.content}
          </span>
          <span className="ml-2 inline-flex translate-y-px items-center gap-1 opacity-0 transition-opacity group-hover/claim:opacity-100">
            {block.feedback !== "none" && (
              <Badge tone={feedbackTone(block.feedback)} size="sm">
                {block.feedback}
              </Badge>
            )}
            {block.corroboration > 0 && (
              <Badge tone="neutral" size="sm" className="tabular-nums" title="independent evidence">
                ×{block.corroboration}
              </Badge>
            )}
            <Badge tone={provenanceTone(block.provenance)} size="sm">
              {provenanceLabel(block.provenance)}
            </Badge>
            <span
              role="button"
              tabIndex={-1}
              onClick={(e) => {
                e.stopPropagation();
                onPeek();
              }}
              className="grid size-[18px] place-items-center rounded text-faint hover:bg-surface-soft hover:text-ink"
              title="Provenance"
            >
              <GitFork size={ICON.XS} strokeWidth={2} />
            </span>
          </span>
        </button>
      )}
    </motion.div>
  );
}

function ClaimEditor({
  block,
  busy,
  onClose,
  onCommit,
}: {
  block: RenderedClaim;
  busy: boolean;
  onClose: () => void;
  onCommit: (op: ClaimOp) => void;
}) {
  const [text, setText] = useState(block.content);
  const taRef = useRef<HTMLTextAreaElement>(null);

  useLayoutEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.focus();
    ta.setSelectionRange(ta.value.length, ta.value.length);
    autosize(ta);
  }, []);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [onClose]);

  const dirty = text.trim() !== block.content.trim() && text.trim().length > 0;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.985 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={SPRING_CARD}
      className="glass-surface surface-popover relative z-10 my-1 p-2.5"
    >
      <textarea
        ref={taRef}
        value={text}
        disabled={busy}
        onChange={(e) => {
          setText(e.target.value);
          autosize(e.target);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && dirty) {
            e.preventDefault();
            onCommit({ kind: "edit", claim_id: block.claim_id, new_text: text.trim() });
          }
        }}
        rows={1}
        spellCheck={false}
        className="w-full resize-none bg-transparent text-sm leading-[1.55] text-ink outline-none placeholder:text-faint"
      />
      <div className="mt-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1">
          <EditorBtn onClick={() => onCommit({ kind: "accept", claim_id: block.claim_id })} disabled={busy} title="Confirm this claim">
            <Check size={ICON.XS} strokeWidth={2.2} /> Accept
          </EditorBtn>
          <EditorBtn
            onClick={() => onCommit({ kind: "reject", claim_id: block.claim_id })}
            disabled={busy}
            danger
            title="Remove from this lens (the claim survives)"
          >
            <X size={ICON.XS} strokeWidth={2.2} /> Remove
          </EditorBtn>
        </div>
        <div className="flex items-center gap-1">
          <EditorBtn onClick={onClose} disabled={busy}>
            Cancel
          </EditorBtn>
          <button
            type="button"
            disabled={busy || !dirty}
            onClick={() => onCommit({ kind: "edit", claim_id: block.claim_id, new_text: text.trim() })}
            title="Supersede with the edited text"
            className="inline-flex h-6 items-center gap-1 rounded-md bg-ink px-2.5 text-xs font-medium text-on-ink transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            <Pencil size={ICON.XS} strokeWidth={2.2} /> Save
          </button>
        </div>
      </div>
    </motion.div>
  );
}

function EditorBtn({
  children,
  onClick,
  disabled,
  danger,
  title,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
  title?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={[
        "inline-flex h-6 items-center gap-1 rounded-md px-2 text-xs text-ink-soft transition-colors disabled:opacity-40",
        danger ? "hover:bg-bad-soft hover:text-bad" : "hover:bg-surface-soft hover:text-ink",
      ].join(" ")}
    >
      {children}
    </button>
  );
}

function autosize(ta: HTMLTextAreaElement) {
  ta.style.height = "auto";
  ta.style.height = `${ta.scrollHeight}px`;
}
