import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ChevronDown } from "lucide-react";
import clsx from "clsx";
import { useShallow } from "zustand/react/shallow";
import { useStore } from "../store";
import { Message } from "./Message";

const EASE = [0.32, 0.72, 0, 1] as const;

function formatDuration(ms: number): string {
  if (ms < 1000) return "less than a second";
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const remS = s % 60;
  if (m < 60) return remS === 0 ? `${m}m` : `${m}m ${remS}s`;
  const h = Math.floor(m / 60);
  const remM = m % 60;
  return remM === 0 ? `${h}h` : `${h}h ${remM}m`;
}

export function TurnGroup({ userId, childIds }: { userId: string; childIds: string[] }) {
  const turn = useStore((s) => s.messages.get(userId)?.turn);

  const finalAssistantId = useStore(
    useShallow((s) => {
      for (let i = childIds.length - 1; i >= 0; i--) {
        const m = s.messages.get(childIds[i]);
        if (m?.role === "assistant") return childIds[i];
      }
      return null;
    }),
  );

  const isDone = turn?.endedAt != null;
  // Default historic turns to collapsed; default in-progress turns to expanded.
  const [expanded, setExpanded] = useState(!isDone);

  // Auto-collapse the moment the run finishes.
  const wasDone = useRef(isDone);
  useEffect(() => {
    if (!wasDone.current && isDone) setExpanded(false);
    wasDone.current = isDone;
  }, [isDone]);

  const interimIds = finalAssistantId
    ? childIds.filter((id) => id !== finalAssistantId)
    : childIds;
  const hasInterim = interimIds.length > 0;
  // Live runs have a real durationMs; historic ones don't (we don't persist
  // turn timing). Show the time when we have it, plain "Worked" otherwise.
  const headerLabel = turn?.durationMs != null
    ? `Worked for ${formatDuration(turn.durationMs)}`
    : "Worked";

  // Single render tree across streaming and done — switching trees on
  // isDone caused every Message to remount, replaying its mount-fade
  // animation. Header fades in once the run ends; interim panel
  // collapses via height animation rather than unmounting; the final
  // assistant message stays at the same DOM position throughout.
  const showInterim = !isDone || expanded;

  return (
    <>
      <Message id={userId} />

      {hasInterim && (
        <div className="flex flex-col">
          <AnimatePresence initial={false}>
            {isDone && (
              <motion.div
                key="header"
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.22, ease: EASE }}
                style={{ overflow: "hidden" }}
              >
                <button
                  type="button"
                  onClick={() => setExpanded((v) => !v)}
                  className="self-start inline-flex items-center gap-1.5 text-[12px] text-faint hover:text-muted transition-colors select-none"
                >
                  <span>{headerLabel}</span>
                  <ChevronDown
                    size={12}
                    strokeWidth={2}
                    className={clsx("transition-transform duration-200", expanded && "rotate-180")}
                  />
                </button>
                <div className="h-px bg-line-soft mt-2.5" />
              </motion.div>
            )}
          </AnimatePresence>

          <motion.div
            initial={false}
            animate={{
              height: showInterim ? "auto" : 0,
              opacity: showInterim ? 1 : 0,
            }}
            transition={{ duration: 0.28, ease: EASE }}
            style={{ overflow: "hidden" }}
          >
            <div className={clsx("flex flex-col gap-3.5", isDone && "pt-3.5")}>
              {interimIds.map((id) => (
                <Message key={id} id={id} isFinal={false} />
              ))}
            </div>
          </motion.div>
        </div>
      )}

      {finalAssistantId && <Message id={finalAssistantId} isFinal={isDone} />}
    </>
  );
}
