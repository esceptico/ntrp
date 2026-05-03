import { useEffect, useRef } from "react";
import { useStore } from "../store";
import { EmptyState } from "./EmptyState";
import { Message } from "./Message";

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

  return (
    <div ref={outerRef} className="min-h-0 overflow-y-auto overflow-x-hidden scroll-messages px-0 pt-7 pb-9">
      <div ref={innerRef} className="messages-inner mx-auto max-w-[760px] min-w-0 px-7 flex flex-col gap-3.5">
        {order.length === 0 ? <EmptyState /> : order.map((id) => <Message key={id} id={id} />)}
      </div>
    </div>
  );
}
