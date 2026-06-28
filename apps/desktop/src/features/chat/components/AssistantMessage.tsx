import { memo } from "react";
import clsx from "clsx";
import { useStore } from "@/stores";
import { Markdown } from "@/components/ui/Markdown";
import { useSmoothStreamedContent } from "@/features/chat/hooks/useSmoothStream";
import { MessageActions } from "@/features/chat/components/MessageActions";
import {
  SOURCE_FOCUS_CLASS,
  entryAnimation,
  useMessage,
  useSourceFocused,
} from "@/features/chat/lib/messageShared";

export const AssistantMessage = memo(function AssistantMessage({ id, isFinal = true }: { id: string; isFinal?: boolean }) {
  const message = useMessage(id);
  const sourceFocused = useSourceFocused(id);
  const running = useStore((s) => s.running);
  const isStreaming = Boolean(message && running && message.turn?.endedAt === null);
  // Hook order rule: call before any conditional return below.
  const smoothContent = useSmoothStreamedContent(message?.content ?? "", isStreaming);
  if (!message) return null;
  // Drop intermediate assistant messages that finished empty — the model
  // opens TEXT_MESSAGE_START before deciding to tool-call instead, leaving
  // a zero-content article that would otherwise stack ~30px of phantom
  // padding inside the work block.
  if (!isFinal && !isStreaming && !message.content.trim()) return null;
  return (
    <article
      className={clsx(
        "assistant-message group grid grid-cols-[minmax(0,1fr)] gap-1.5 min-w-0 transition-[background-color,box-shadow] duration-panel",
        entryAnimation(message, "animate-fade-in"),
        sourceFocused && SOURCE_FOCUS_CLASS,
      )}
      data-streaming={isStreaming ? "true" : undefined}
      data-id={id}
      data-source-focus={sourceFocused ? "true" : undefined}
      data-source-index={message.sourceIndex}
    >
      <Markdown
        content={smoothContent}
        streaming={isStreaming}
        className="text-base leading-[1.5] text-ink break-words"
      />
      {isFinal && <MessageActions id={id} role="assistant" />}
    </article>
  );
});
