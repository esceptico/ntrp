import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ChevronDown } from "lucide-react";
import { useStickToBottom } from "use-stick-to-bottom";
import { useShallow } from "zustand/react/shallow";
import { useStore } from "../store";
import { messagesScroll } from "../lib/messagesScroll";
import { EmptyState } from "./EmptyState";
import { Message } from "./Message";
import { CompactionIndicator } from "./CompactionIndicator";
import { TurnGroup } from "./TurnGroup";

// Parent (Chat) remounts this component on session change via key={sessionId}
// so each session starts fresh — no carryover scroll state.
export function Messages() {
  const order = useStore((s) => s.order);

  const { scrollRef, contentRef, scrollToBottom, isNearBottom } = useStickToBottom({
    initial: "instant",
    resize: "smooth",
  });

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

  // Expose for actions.sendMessage to force-scroll on user send.
  useEffect(() => {
    messagesScroll.scrollToBottom = (behavior) =>
      scrollToBottom({ animation: behavior === "instant" ? "instant" : "smooth" });
    return () => {
      messagesScroll.scrollToBottom = null;
    };
  }, [scrollToBottom]);

  const roles = useStore(
    useShallow((s) => order.map((id) => s.messages.get(id)?.role ?? null)),
  );

  const segments = useMemo(() => {
    type Segment = { userId: string | null; childIds: string[] };
    const out: Segment[] = [];
    let current: Segment | null = null;
    for (let i = 0; i < order.length; i++) {
      const id = order[i];
      const role = roles[i];
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
  }, [order, roles]);

  return (
    <div className="relative min-h-0">
      <div ref={scrollRef} className="absolute inset-0 overflow-y-auto overflow-x-hidden scroll-messages px-0 pt-7 pb-9">
        <div ref={contentRef} className="messages-inner mx-auto max-w-[760px] min-w-0 px-7 flex flex-col gap-3.5">
          {order.length === 0
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
            transition={{ duration: 0.16, ease: [0.32, 0.72, 0, 1] }}
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
