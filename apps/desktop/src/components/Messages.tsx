import { useEffect, useMemo, useRef } from "react";
import { useShallow } from "zustand/react/shallow";
import { useStore } from "../store";
import { EmptyState } from "./EmptyState";
import { Message } from "./Message";
import { ThinkingIndicator } from "./ThinkingIndicator";
import { CompactionIndicator } from "./CompactionIndicator";
import { TurnGroup } from "./TurnGroup";

function isAtBottom(el: Element, threshold = 64): boolean {
  return el.scrollTop + el.clientHeight >= el.scrollHeight - threshold;
}

export function Messages() {
  const order = useStore((s) => s.order);
  const sessionId = useStore((s) => s.currentSessionId);
  const outerRef = useRef<HTMLDivElement>(null);
  const innerRef = useRef<HTMLDivElement>(null);
  const stuckRef = useRef(true);

  // Track if user is at the bottom.
  useEffect(() => {
    const outer = outerRef.current;
    if (!outer) return;
    const handler = () => {
      stuckRef.current = isAtBottom(outer);
    };
    outer.addEventListener("scroll", handler, { passive: true });
    return () => outer.removeEventListener("scroll", handler);
  }, []);

  // Snap to bottom whenever inner content grows, only if user was already at the bottom.
  useEffect(() => {
    const outer = outerRef.current;
    const inner = innerRef.current;
    if (!outer || !inner) return;
    const ro = new ResizeObserver(() => {
      if (stuckRef.current) outer.scrollTop = outer.scrollHeight;
    });
    ro.observe(inner);
    return () => ro.disconnect();
  }, []);

  // Session switch: force snap to bottom and reset stuck flag.
  useEffect(() => {
    stuckRef.current = true;
    const outer = outerRef.current;
    if (outer) outer.scrollTop = outer.scrollHeight;
  }, [sessionId]);

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
    <div ref={outerRef} className="min-h-0 overflow-y-auto overflow-x-hidden scroll-messages px-0 pt-7 pb-9">
      <div ref={innerRef} className="messages-inner mx-auto max-w-[760px] min-w-0 px-7 flex flex-col gap-3.5">
        {order.length === 0
          ? <EmptyState />
          : segments.map((seg) =>
              seg.userId
                ? <TurnGroup key={seg.userId} userId={seg.userId} childIds={seg.childIds} />
                : <div key="preamble" className="contents">{seg.childIds.map((id) => <Message key={id} id={id} />)}</div>
            )}
        <CompactionIndicator />
        <ThinkingIndicator />
      </div>
    </div>
  );
}
