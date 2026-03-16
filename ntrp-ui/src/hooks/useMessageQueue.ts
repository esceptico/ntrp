import { useState, useEffect, useCallback, useRef } from "react";
import type { ImageBlock } from "../api/chat.js";

interface QueueEntry {
  message: string;
  images?: ImageBlock[];
}

export function useMessageQueue(
  isStreaming: boolean,
  pendingApproval: unknown,
  sendMessage: (msg: string, images?: ImageBlock[]) => void,
) {
  const [messageQueue, setMessageQueue] = useState<QueueEntry[]>([]);
  const drainingRef = useRef(false);

  const enqueue = useCallback((msg: string, images?: ImageBlock[]) => {
    setMessageQueue((prev) => [...prev, { message: msg, images }]);
  }, []);

  const clearQueue = useCallback(() => {
    setMessageQueue([]);
  }, []);

  useEffect(() => {
    if (drainingRef.current) return;
    if (!isStreaming && !pendingApproval && messageQueue.length > 0) {
      drainingRef.current = true;
      const [first, ...rest] = messageQueue;
      setMessageQueue(rest);
      if (first) sendMessage(first.message, first.images);
      drainingRef.current = false;
    }
  }, [isStreaming, pendingApproval, messageQueue, sendMessage]);

  return { messageQueue, enqueue, clearQueue };
}
