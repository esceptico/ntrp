import { motion } from "motion/react";
import { Check, Pencil, Target, X } from "lucide-react";
import { acceptGoalProposal, cancelGoalProposal, editGoalProposal } from "@/actions/goals";
import { ICON } from "@/lib/icons";
import { RISE_IN, RISE_SETTLED } from "@/lib/tokens/motion";
import { SECTION_ENTER, SECTION_EXIT } from "@/features/chat/lib/composerMotion";

export function GoalProposalCard({ objective }: { objective: string }) {
  return (
    <motion.div
      initial={RISE_IN}
      animate={RISE_SETTLED}
      exit={SECTION_EXIT}
      transition={SECTION_ENTER}
      className="max-w-[760px] mx-auto mb-2"
    >
      <div className="surface-panel surface-radius-md flex items-start gap-2 px-3 py-2">
        <Target size={ICON.MD} strokeWidth={2} className="mt-0.5 shrink-0 text-accent" />
        <div className="min-w-0 flex-1">
          <div className="text-2xs font-medium text-muted">Proposed goal</div>
          <div className="max-h-10 overflow-hidden text-sm leading-5 text-ink-soft">{objective}</div>
        </div>
        <button
          type="button"
          onClick={() => void acceptGoalProposal()}
          title="Accept goal"
          aria-label="Accept goal"
          className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-ink text-on-ink hover:opacity-90 transition-[opacity,scale] duration-check ease-out active:scale-[0.94]"
        >
          <Check size={ICON.SM} strokeWidth={2.4} />
        </button>
        <button
          type="button"
          onClick={editGoalProposal}
          title="Edit goal"
          aria-label="Edit goal"
          className="grid h-7 w-7 shrink-0 place-items-center rounded-full text-muted hover:bg-surface-soft hover:text-ink transition-[background-color,color,scale] duration-check ease-out active:scale-[0.94]"
        >
          <Pencil size={ICON.SM} strokeWidth={2} />
        </button>
        <button
          type="button"
          onClick={cancelGoalProposal}
          title="Cancel goal"
          aria-label="Cancel goal"
          className="grid h-7 w-7 shrink-0 place-items-center rounded-full text-muted hover:bg-surface-soft hover:text-ink transition-[background-color,color,scale] duration-check ease-out active:scale-[0.94]"
        >
          <X size={ICON.SM} strokeWidth={2} />
        </button>
      </div>
    </motion.div>
  );
}
