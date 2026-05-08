import { useCallback, useEffect, useLayoutEffect, useMemo, useRef } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ChevronDown } from "lucide-react";
import { useStickToBottom } from "use-stick-to-bottom";
import { useShallow } from "zustand/react/shallow";
import { useStore } from "../store";
import { messagesScroll } from "../lib/messagesScroll";
import { visibleMessageIds } from "../lib/messageVisibility";
import { firstMessageIdInSourceFocus } from "../lib/messageSourceFocus";
import { loadNewerHistory, loadOlderHistory } from "../actions";
import { MOTION, EASE_EMPHASIZED } from "../lib/motion";
import { EmptyState } from "./EmptyState";
import { Message } from "./Message";
import { CompactionIndicator } from "./CompactionIndicator";
import { TurnGroup } from "./TurnGroup";

// Parent (Chat) remounts this component on session change via key={sessionId}
// so each session starts fresh — no carryover scroll state.
export function Messages() {
  const order = useStore((s) => s.order);
  const currentSessionId = useStore((s) => s.currentSessionId);
  const historyLoadedFor = useStore((s) => s.historyLoadedFor);
  const sourceFocus = useStore((s) => s.sourceFocus);
  const historyPaging = useStore(
    useShallow((s) => ({
      hasMoreBefore: s.historyHasMoreBefore,
      hasMoreAfter: s.historyHasMoreAfter,
      loadingBefore: s.historyLoadingBefore,
      loadingAfter: s.historyLoadingAfter,
    })),
  );
  const sessionReady = currentSessionId === null || historyLoadedFor === currentSessionId;
  const firstSourceFocusId = useStore((s) =>
    firstMessageIdInSourceFocus(s.order, s.messages, s.sourceFocus, s.currentSessionId),
  );

  // Streaming smooth-scroll. Spring tuned for "river of text" feel — low
  // stiffness + high damping so scroll trails the latest content gently
  // instead of snapping or overshooting. Spec: docs/internal/apple-design-
  // intel.md and https://github.com/StonkDog/use-stick-to-bottom.
  const { scrollRef, contentRef, scrollToBottom, isNearBottom } = useStickToBottom({
    initial: "instant",
    resize: { damping: 0.92, stiffness: 0.025, mass: 1.5 },
  });
  const topAnchorRef = useRef<{ height: number; top: number } | null>(null);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (el.scrollTop < 120 && historyPaging.hasMoreBefore && !historyPaging.loadingBefore) {
      topAnchorRef.current = { height: el.scrollHeight, top: el.scrollTop };
      void loadOlderHistory();
    }

    const bottomGap = el.scrollHeight - el.clientHeight - el.scrollTop;
    if (bottomGap < 120 && historyPaging.hasMoreAfter && !historyPaging.loadingAfter) {
      void loadNewerHistory();
    }
  }, [historyPaging.hasMoreAfter, historyPaging.hasMoreBefore, historyPaging.loadingAfter, historyPaging.loadingBefore, scrollRef]);

  // First time content lands after mount (loadHistory fills `order`),
  // snap instantly. Without this, the library treats the empty→full
  // growth as a resize and smooth-scrolls from 0 to bottom — visible
  // as a "scroll from the top" on session switch.
  const seenContentRef = useRef(false);
  useLayoutEffect(() => {
    if (seenContentRef.current || order.length === 0) return;
    seenContentRef.current = true;
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
    scrollToBottom({ animation: "instant" });
  }, [order.length, scrollRef, scrollToBottom]);

  useLayoutEffect(() => {
    const anchor = topAnchorRef.current;
    const el = scrollRef.current;
    if (!anchor || !el) return;
    el.scrollTop = el.scrollHeight - anchor.height + anchor.top;
    topAnchorRef.current = null;
  }, [order.length, scrollRef]);

  // Expose for actions.sendMessage to force-scroll on user send.
  useEffect(() => {
    messagesScroll.scrollToBottom = (behavior) =>
      scrollToBottom({ animation: behavior === "instant" ? "instant" : "smooth" });
    return () => {
      messagesScroll.scrollToBottom = null;
    };
  }, [scrollToBottom]);

  useEffect(() => {
    if (!sourceFocus || sourceFocus.sessionId !== currentSessionId || !firstSourceFocusId) return;
    const frame = requestAnimationFrame(() => {
      const target = scrollRef.current?.querySelector<HTMLElement>('[data-source-focus="true"]');
      target?.scrollIntoView({ block: "center", behavior: "smooth" });
    });
    return () => cancelAnimationFrame(frame);
  }, [currentSessionId, firstSourceFocusId, scrollRef, sourceFocus]);

  const roles = useStore(
    useShallow((s) => order.map((id) => s.messages.get(id)?.role ?? null)),
  );
  const showReasoning = useStore((s) => s.prefs.showReasoningInChat);

  const visibleOrder = useMemo(
    () => visibleMessageIds({ ids: order, roles, showReasoning }),
    [order, roles, showReasoning],
  );

  const roleById = useMemo(() => {
    const out = new Map<string, typeof roles[number]>();
    for (let i = 0; i < order.length; i++) out.set(order[i], roles[i]);
    return out;
  }, [order, roles]);

  const segments = useMemo(() => {
    type Segment = { userId: string | null; childIds: string[] };
    const out: Segment[] = [];
    let current: Segment | null = null;
    for (const id of visibleOrder) {
      const role = roleById.get(id);
      if (role === "user") {
        if (current) out.push(current);
        current = { userId: id, childIds: [] };
      } else {
        if (!current) current = { userId: null, childIds: [] };
        current.childIds.push(id);
      }
    }
    if (current) out.push(current);
    return out;
  }, [roleById, visibleOrder]);

  return (
    <div className="relative min-h-0">
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="absolute inset-0 overflow-y-auto overflow-x-hidden scroll-messages px-0 pt-7 pb-9"
      >
        <div ref={contentRef} className="messages-inner mx-auto max-w-[760px] min-w-0 px-7 flex flex-col gap-6">
          {!sessionReady
            ? null
            : visibleOrder.length === 0
              ? <EmptyState />
              : segments.map((seg) =>
                  seg.userId
                    ? <TurnGroup key={seg.userId} userId={seg.userId} childIds={seg.childIds} />
                    : <div key="preamble" className="contents">{seg.childIds.map((id) => <Message key={id} id={id} />)}</div>
                )}
          <CompactionIndicator />
        </div>
      </div>
      <AnimatePresence>
        {!isNearBottom && order.length > 0 && (
          <motion.button
            type="button"
            onClick={() => scrollToBottom({ animation: "smooth" })}
            initial={{ opacity: 0, y: 6, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 6, scale: 0.95 }}
            transition={{ duration: MOTION.row, ease: EASE_EMPHASIZED }}
            aria-label="Scroll to bottom"
            className="scroll-to-bottom absolute left-1/2 -translate-x-1/2 bottom-3 grid place-items-center w-8 h-8 rounded-full text-muted hover:text-ink"
          >
            <ChevronDown size={16} strokeWidth={1.8} />
          </motion.button>
        )}
      </AnimatePresence>
    </div>
  );
}
