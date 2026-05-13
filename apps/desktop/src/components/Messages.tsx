import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
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
import { ICON } from "../lib/icons";

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
  const { scrollRef, contentRef, scrollToBottom, stopScroll, isNearBottom } = useStickToBottom({
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

  // Intent-aware "new messages while detached" counter. While the user
  // is near-bottom, advance `seenLastIdRef` to the tail — that's the
  // marker for "everything up to here has been seen." When they scroll
  // up, the marker freezes; the count is the number of ids appended
  // after it. History paging prepends to `order`, so counting by tail
  // index (not raw length) is critical — older-history loads grow the
  // array but don't add unread material.
  const seenLastIdRef = useRef<string | null>(null);
  const [unreadCount, setUnreadCount] = useState(0);
  useEffect(() => {
    const lastId = order[order.length - 1] ?? null;
    if (isNearBottom) {
      seenLastIdRef.current = lastId;
      if (unreadCount !== 0) setUnreadCount(0);
      return;
    }
    // Detached. Anchor the marker on first transition into this state
    // so we count only what arrives going forward.
    if (!seenLastIdRef.current) {
      seenLastIdRef.current = lastId;
      return;
    }
    const seenIdx = order.indexOf(seenLastIdRef.current);
    if (seenIdx === -1) {
      // Marker fell out of `order` (history replay / session reload).
      // Re-anchor and stop counting from now.
      seenLastIdRef.current = lastId;
      if (unreadCount !== 0) setUnreadCount(0);
      return;
    }
    const tail = order.length - 1 - seenIdx;
    if (tail !== unreadCount) setUnreadCount(tail);
  }, [order, isNearBottom, unreadCount]);

  const onPillClick = useCallback(() => {
    setUnreadCount(0);
    scrollToBottom({ animation: "smooth" });
  }, [scrollToBottom]);

  const roles = useStore(
    useShallow((s) => order.map((id) => s.messages.get(id)?.role ?? null)),
  );
  const metaFlags = useStore(
    useShallow((s) => order.map((id) => Boolean(s.messages.get(id)?.isMeta))),
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

  const metaById = useMemo(() => {
    const out = new Map<string, boolean>();
    for (let i = 0; i < order.length; i++) out.set(order[i], metaFlags[i]);
    return out;
  }, [order, metaFlags]);

  const segments = useMemo(() => {
    type Segment = { userId: string | null; childIds: string[] };
    const out: Segment[] = [];
    let current: Segment | null = null;
    for (const id of visibleOrder) {
      const role = roleById.get(id);
      if (role === "user") {
        // Meta user messages (loop ticks) are hidden from the transcript
        // but still segment-anchor: close the current segment and start
        // a fresh null-userId one so the agent's response renders cleanly
        // without being grouped under the previous user's "Worked" block.
        if (metaById.get(id)) {
          if (current) out.push(current);
          current = { userId: null, childIds: [] };
          continue;
        }
        if (current) out.push(current);
        current = { userId: id, childIds: [] };
      } else if (role === "status" || role === "error") {
        // System notices (from builtin slash commands like /loop, /clear)
        // are not children of any turn — surface them between turns so
        // they don't get buried inside the previous turn's "Worked" collapse.
        if (current) {
          out.push(current);
          current = null;
        }
        out.push({ userId: null, childIds: [id] });
      } else {
        if (!current) current = { userId: null, childIds: [] };
        current.childIds.push(id);
      }
    }
    if (current) out.push(current);
    return out;
  }, [roleById, metaById, visibleOrder]);

  return (
    <div className="relative min-h-0">
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="absolute inset-0 overflow-y-auto overflow-x-hidden scroll-messages px-0 pt-7 pb-9"
      >
        <div ref={contentRef} className="messages-inner mx-auto max-w-[760px] min-w-0 px-7 flex flex-col gap-3">
          {!sessionReady
            ? null
            : visibleOrder.length === 0
              ? <EmptyState />
              : segments.map((seg) =>
                  seg.userId
                    ? <TurnGroup key={seg.userId} userId={seg.userId} childIds={seg.childIds} onManualResize={stopScroll} />
                    : <div key="preamble" className="contents">{seg.childIds.map((id) => <Message key={id} id={id} />)}</div>
                )}
          <CompactionIndicator />
        </div>
      </div>
      <AnimatePresence>
        {!isNearBottom && order.length > 0 && (
          <motion.button
            type="button"
            onClick={onPillClick}
            initial={{ opacity: 0, y: 6, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 6, scale: 0.95 }}
            transition={{ duration: MOTION.row, ease: EASE_EMPHASIZED }}
            aria-label={unreadCount > 0 ? `${unreadCount} new message${unreadCount === 1 ? "" : "s"} — jump to latest` : "Scroll to bottom"}
            // Pill grows to fit a count badge when messages land while
            // the user is scrolled up. With zero unread we collapse back
            // to the round chevron — minimal chrome when there's nothing
            // to communicate. `layout` lets motion FLIP between widths.
            layout
            className={
              unreadCount > 0
                ? "absolute left-1/2 -translate-x-1/2 bottom-3 inline-flex items-center gap-1.5 h-8 pl-2.5 pr-3 rounded-full bg-ink text-on-ink border border-transparent shadow-[0_1px_2px_rgba(0,0,0,0.08),0_6px_18px_rgba(0,0,0,0.12)] text-sm font-medium hover:opacity-90 transition-opacity"
                : "absolute left-1/2 -translate-x-1/2 bottom-3 grid place-items-center w-8 h-8 rounded-full bg-surface text-muted border border-black/[0.08] shadow-[0_1px_2px_rgba(0,0,0,0.04),0_4px_12px_rgba(0,0,0,0.06)] transition-[background-color,color,transform] duration-fast hover:text-ink hover:bg-surface-soft dark:border-white/[0.08] dark:shadow-[0_1px_2px_rgba(0,0,0,0.4),0_4px_14px_rgba(0,0,0,0.35)]"
            }
          >
            <ChevronDown size={ICON.MD} strokeWidth={1.8} />
            {unreadCount > 0 && (
              <motion.span
                key={unreadCount}
                initial={{ opacity: 0, y: -3 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.14, ease: EASE_EMPHASIZED }}
                className="tabular-nums"
              >
                {unreadCount} new
              </motion.span>
            )}
          </motion.button>
        )}
      </AnimatePresence>
    </div>
  );
}
