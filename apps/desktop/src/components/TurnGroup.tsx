import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ChevronDown } from "lucide-react";
import clsx from "clsx";
import { useShallow } from "zustand/react/shallow";
import { useStore } from "../store";
import { Message } from "./Message";
import { turnLayout } from "../lib/turnLayout";
import { turnHeaderLabel } from "../lib/turnHeader";
import { turnHasActiveChildAgent } from "../lib/turnActiveAgents";
import { MOTION, EASE_EMPHASIZED, SPRING_ROW_ENTRY } from "../lib/tokens/motion";
import { ICON } from "../lib/icons";

const EASE = EASE_EMPHASIZED;

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
  const motionDisabled = useStore((s) =>
    Boolean(s.messages.get(userId)?.suppressEntryMotion || s.streamReplaying),
  );

  const childSummaryKeys = useStore(
    useShallow((s) =>
      childIds.map((id) => {
        const message = s.messages.get(id);
        return `${message?.role ?? ""}\t${message?.activity?.label ?? ""}`;
      }),
    ),
  );
  const childSummaries = useMemo(
    () =>
      childSummaryKeys.map((key) => {
        const [role, activityLabel] = key.split("\t");
        return {
          role: role || null,
          activityLabel: activityLabel || null,
        };
      }),
    [childSummaryKeys],
  );
  const children = useMemo(
    () => childIds.map((id, index) => ({ id, role: childSummaries[index]?.role ?? null })),
    [childIds, childSummaries],
  );

  // Only group into a "Worked Xs" block when the turn actually invoked
  // tools. A turn with just reasoning + a final reply has no work to
  // collapse — render its children inline instead.
  const hasTools = children.some((child) => child.role === "activity");

  const hasActiveChildAgent = useStore((s) =>
    turnHasActiveChildAgent({
      childIds,
      messages: s.messages,
      backgroundAgents: s.backgroundAgents.rows,
      sessionId: s.currentSessionId,
    }),
  );
  const isDone = turn?.endedAt != null && !hasActiveChildAgent;
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
  const wasStopped = childSummaries.some((child) => child.activityLabel === "Stopped");
  const headerLabel = turnHeaderLabel(turn?.durationMs, wasStopped);

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
  // inherit the steady state directly. Hydrated/replayed turns disable
  // this initial stagger; live rows keep their per-article entry motion.
  const interimList = (
    <motion.div
      initial={motionDisabled ? false : "hidden"}
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
          variants={
            motionDisabled
              ? undefined
              : {
                  hidden: { opacity: 0, y: 4 },
                  visible: { opacity: 1, y: 0 },
                }
          }
          transition={motionDisabled ? { duration: 0 } : SPRING_ROW_ENTRY}
        >
          <Message id={id} isFinal={false} />
        </motion.div>
      ))}
    </motion.div>
  );
  const workBlock = hasWork ? (
    <div className="flex flex-col">
      {/* grid-template-rows: 0fr ↔ 1fr lets the row collapse without ever
          animating `height: auto`, which would trigger layout recalc every
          frame (D-tier per motion's tier list). The inner wrapper is grid
          item 1 with overflow:hidden + min-height:0 so the row defines its
          own clip. */}
      <AnimatePresence initial={false}>
        {isDone && (
          <motion.div
            key="header"
            initial={{ gridTemplateRows: "0fr", opacity: 0 }}
            animate={{ gridTemplateRows: "1fr", opacity: 1 }}
            exit={{ gridTemplateRows: "0fr", opacity: 0 }}
            transition={{ duration: MOTION.panel, ease: EASE }}
            style={{ display: "grid" }}
          >
            <div style={{ overflow: "hidden", minHeight: 0 }}>
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
                  className={clsx("transition-transform duration-trace", expanded && "rotate-180")}
                />
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {isDone ? (
        <motion.div
          initial={false}
          animate={{
            gridTemplateRows: showInterim ? "1fr" : "0fr",
            opacity: showInterim ? 1 : 0,
          }}
          transition={{ duration: MOTION.route, ease: EASE }}
          style={{ display: "grid" }}
        >
          <div style={{ overflow: "hidden", minHeight: 0 }}>
            <div className="h-px bg-line-soft mt-2" />
            {interimList}
          </div>
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
