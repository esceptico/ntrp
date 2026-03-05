import { useState, useEffect, useCallback, useRef } from "react";

export function useMessageQueue(
  isStreaming: boolean,
  pendingApproval: unknown,
  sendMessage: (msg: string) => void,
) {
  const [messageQueue, setMessageQueue] = useState<string[]>([]);
  const drainingRef = useRef(false);

  const enqueue = useCallback((msg: string) => {
    setMessageQueue((prev) => [...prev, msg]);
  }, []);

  const clearQueue = useCallback(() => {
    setMessageQueue([]);
  }, []);

  useEffect(() => {
    if (drainingRef.current) return;
    if (!isStreaming && !pendingApproval && messageQueue.length > 0) {
      drainingRef.current = true;
      const [firstMessage, ...rest] = messageQueue;
      setMessageQueue(rest);
      if (firstMessage) sendMessage(firstMessage);
      drainingRef.current = false;
    }
  }, [isStreaming, pendingApproval, messageQueue, sendMessage]);

  return { messageQueue, enqueue, clearQueue };
}
