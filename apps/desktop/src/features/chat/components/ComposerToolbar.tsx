import { AnimatePresence, motion } from "motion/react";
import { ArrowUp, ImagePlus, ShieldOff, ShieldCheck, Square } from "lucide-react";
import clsx from "clsx";
import { Chip } from "@/components/ui/Chip";
import { BlurSwap } from "@/components/ui/BlurSwap";
import { ModelReasoningChip } from "@/components/ui/ComposerSelectors";
import { IconButton } from "@/components/ui/IconButton";
import { GoalStatusBar } from "@/features/chat/components/GoalStrip";
import { LoopStatusBar } from "@/features/chat/components/LoopStatus";
import { BudgetDial } from "@/features/chat/components/BudgetDial";
import { ICON } from "@/lib/icons";
import { EASE_OUT, MOTION } from "@/lib/tokens/motion";

export function ComposerToolbar({
  onAttach,
  skipApprovals,
  onToggleAuto,
  running,
  sendDisabled,
  sendPressing,
  onStop,
}: {
  onAttach: () => void;
  skipApprovals: boolean;
  onToggleAuto: () => void;
  running: boolean;
  sendDisabled: boolean;
  sendPressing: boolean;
  onStop: () => void;
}) {
  return (
    <div className="composer-toolbar flex items-center gap-1.5 px-2 pt-1.5 pb-2">
      <IconButton
        shape="circle"
        onClick={onAttach}
        aria-label="Attach image"
        title="Attach image"
      >
        <ImagePlus size={ICON.LG} strokeWidth={2} />
      </IconButton>
      <Chip
        size="sm"
        active={skipApprovals}
        tone="accent"
        leading={
          <BlurSwap swapKey={skipApprovals ? "auto" : "approve"}>
            {skipApprovals ? <ShieldOff size={ICON.SM} strokeWidth={2} /> : <ShieldCheck size={ICON.SM} strokeWidth={2} />}
          </BlurSwap>
        }
        onClick={onToggleAuto}
        title={skipApprovals ? "Auto-approving every tool call. Click to require approval." : "Approvals required for sensitive tools. Click to enable Auto mode."}
        aria-label={skipApprovals ? "Auto-approve enabled — click to require approval" : "Click to enable auto-approve"}
      >
        <span className="composer-chip-label">{skipApprovals ? "Auto" : "Approve"}</span>
      </Chip>
      <LoopStatusBar />
      <GoalStatusBar />
      <span className="flex-1" />
      <BudgetDial />
      <ModelReasoningChip />
      {/* One persistent button so the glyph genuinely swaps (rotate+fade)
          between send and stop instead of the button remounting. */}
      <button
        type={running ? "button" : "submit"}
        onClick={running ? onStop : undefined}
        disabled={!running && sendDisabled}
        data-send={running ? undefined : "true"}
        aria-label={running ? "Stop" : "Send"}
        title={running ? "Stop (Esc)" : undefined}
        // active:scale handles mouse press; sendPressing covers keyboard
        // Enter (form-submit doesn't fire :active). Both look identical.
        className={clsx(
          "grid place-items-center w-7 h-7 rounded-full bg-ink text-on-ink shadow-sm hover:opacity-90 disabled:opacity-[0.45] disabled:shadow-none transition-[opacity,scale] duration-fast ease-out active:scale-[0.92]",
          sendPressing && "scale-[0.92]",
        )}
      >
        <AnimatePresence initial={false}>
          <motion.span
            key={running ? "stop" : "send"}
            className="col-start-1 row-start-1 grid place-items-center"
            initial={{ opacity: 0, rotate: -18, scale: 0.92, filter: "blur(4px)" }}
            animate={{ opacity: 1, rotate: 0, scale: 1, filter: "blur(0px)" }}
            exit={{ opacity: 0, rotate: 18, scale: 0.92, filter: "blur(4px)" }}
            transition={{ duration: MOTION.palette, ease: EASE_OUT }}
          >
            {running ? (
              <Square size={ICON.SM} strokeWidth={0} fill="currentColor" />
            ) : (
              <ArrowUp size={ICON.LG} strokeWidth={2.4} />
            )}
          </motion.span>
        </AnimatePresence>
      </button>
    </div>
  );
}
