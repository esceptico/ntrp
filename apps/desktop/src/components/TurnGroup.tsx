import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ChevronDown } from "lucide-react";
import clsx from "clsx";
import { useShallow } from "zustand/react/shallow";
import { useStore } from "../store";
import { Message } from "./Message";
import { turnLayout } from "../lib/turnLayout";
import { MOTION, EASE_EMPHASIZED } from "../lib/motion";

const EASE = EASE_EMPHASIZED;

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

export function TurnGroup({
  userId,
  childIds,
  onManualResize,
}: {
  userId: string;
  childIds: string[];
  onManualResize?: () => void;
}) {
  const turn = useStore((s) => s.messages.get(userId)?.turn);

  const childRoles = useStore(
    useShallow((s) => childIds.map((id) => s.messages.get(id)?.role ?? null)),
  );
  const children = useMemo(
    () => childIds.map((id, index) => ({ id, role: childRoles[index] ?? null })),
    [childIds, childRoles],
  );

  // Only group into a "Worked Xs" block when the turn actually invoked
  // tools. A turn with just reasoning + a final reply has no work to
  // collapse — render its children inline instead.
  const hasTools = children.some((child) => child.role === "activity");

  const isDone = turn?.endedAt != null;
  // Default historic turns to collapsed; default in-progress turns to expanded.
  const [expanded, setExpanded] = useState(!isDone);

  // Auto-collapse the moment the run finishes.
  const wasDone = useRef(isDone);
  useEffect(() => {
    if (!wasDone.current && isDone) setExpanded(false);
    wasDone.current = isDone;
  }, [isDone]);

  const layout = hasTools
    ? turnLayout({ children, isDone })
    : {
        workIds: [],
        afterWorkIds: childIds,
        finalAssistantId: lastAssistantId(children),
      };
  const hasWork = layout.workIds.length > 0;
  // Live runs have a real durationMs; historic ones don't (we don't persist
  // turn timing). Show the time when we have it, plain "Worked" otherwise.
  const headerLabel = turn?.durationMs != null
    ? `Worked for ${formatDuration(turn.durationMs)}`
    : "Worked";

  const showInterim = !isDone || expanded;
  const interimList = (
    <div className={clsx("flex flex-col gap-3.5", isDone && "pt-1.5")}>
      {layout.workIds.map((id) => (
        <Message key={id} id={id} isFinal={false} />
      ))}
    </div>
  );
  const workBlock = hasWork ? (
    <div className="flex flex-col">
      <AnimatePresence initial={false}>
        {isDone && (
          <motion.div
            key="header"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: MOTION.panel, ease: EASE }}
            style={{ overflow: "hidden" }}
          >
            <button
              type="button"
              onClick={() => {
                onManualResize?.();
                setExpanded((v) => !v);
              }}
              className="self-start inline-flex items-center gap-1.5 text-[14.5px] leading-[1.45] text-muted hover:text-ink-soft transition-colors select-none"
            >
              <span>{headerLabel}</span>
              <ChevronDown
                size={13}
                strokeWidth={2}
                className={clsx("transition-transform duration-200", expanded && "rotate-180")}
              />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {isDone ? (
        <motion.div
          initial={false}
          animate={{
            height: showInterim ? "auto" : 0,
            opacity: showInterim ? 1 : 0,
          }}
          transition={{ duration: MOTION.route, ease: EASE }}
          style={{ overflow: "hidden" }}
        >
          <div className="h-px bg-line-soft mt-2" />
          {interimList}
        </motion.div>
      ) : (
        interimList
      )}
    </div>
  ) : null;

  return (
    <div className="flex flex-col gap-2.5">
      <Message id={userId} />

      {isDone && workBlock}

      {layout.afterWorkIds.map((id) => (
        <Message key={id} id={id} isFinal={isDone && id === layout.finalAssistantId} />
      ))}

      {!isDone && workBlock}
    </div>
  );
}

function lastAssistantId(children: { id: string; role: string | null }[]): string | null {
  for (let i = children.length - 1; i >= 0; i--) {
    if (children[i].role === "assistant") return children[i].id;
  }
  return null;
}
