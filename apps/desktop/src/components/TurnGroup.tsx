import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ChevronDown } from "lucide-react";
import clsx from "clsx";
import { useShallow } from "zustand/react/shallow";
import { useStore } from "../store";
import { Message } from "./Message";
import { turnLayout } from "../lib/turnLayout";
import { MOTION, EASE_EMPHASIZED, SPRING_ROW_ENTRY } from "../lib/motion";
import { ICON } from "../lib/icons";

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
  // Stagger sibling reveals per Rauno's Depth essay ("Stagger sibling
  // fades — Synchronous fade hides quantity; stagger by ~30–60ms").
  //
  // Variant `animate` is gated on `showInterim` so the stagger plays
  // when the parent's collapse opens (Path A: user clicks "Worked for
  // Xs" on a finished turn), not silently under a height:0 mask on
  // initial mount. For live turns `showInterim` is true from the start,
  // so the initial paint also plays the stagger if multiple workIds
  // mount in the same render.
  //
  // Streaming arrivals (workIds added one-by-one over time) don't get
  // motion stagger — parent is already at "visible" so new children
  // inherit the steady state directly. Their existing per-article CSS
  // `animate-roll-in` keyframe still fires, so they keep their entry
  // animation as before. We intentionally do NOT suppress that CSS,
  // because it's the only entry animation for streaming arrivals.
  const interimList = (
    <motion.div
      initial="hidden"
      animate={showInterim ? "visible" : "hidden"}
      variants={{
        hidden: {},
        visible: { transition: { staggerChildren: 0.045 } },
      }}
      className={clsx("flex flex-col gap-3.5", isDone && "pt-1.5")}
    >
      {layout.workIds.map((id) => (
        <motion.div
          key={id}
          variants={{
            hidden: { opacity: 0, y: 4 },
            visible: { opacity: 1, y: 0 },
          }}
          transition={SPRING_ROW_ENTRY}
        >
          <Message id={id} isFinal={false} />
        </motion.div>
      ))}
    </motion.div>
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
              className="self-start inline-flex items-center gap-1.5 text-base leading-[1.45] text-muted hover:text-ink-soft transition-colors select-none"
            >
              <span>{headerLabel}</span>
              <ChevronDown
                size={ICON.XS}
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
