import { memo } from "react";
import type { Message } from "../../../types.js";
import { ToolChainDisplay, type ToolChainItem } from "../../ToolChain.js";
import { UserMessage } from "./UserMessage.js";
import { AssistantMessage } from "./AssistantMessage.js";
import { ToolMessage } from "./ToolMessage.js";
import { StatusMessage } from "./StatusMessage.js";
import { ErrorMessage } from "./ErrorMessage.js";
import { ThinkingMessage } from "./ThinkingMessage.js";

interface MessageDisplayProps {
  msg: Message;
  renderMarkdown?: boolean;
}

export const MessageDisplay = memo(function MessageDisplay({
  msg,
  renderMarkdown = true,
}: MessageDisplayProps) {
  switch (msg.role) {
    case "user":
      return <UserMessage content={msg.content} />;
    case "assistant":
      return (
        <AssistantMessage
          content={msg.content}
          renderMarkdown={renderMarkdown}
        />
      );
    case "tool":
      return (
        <ToolMessage
          name={msg.toolName || "tool"}
          content={msg.content}
          description={msg.toolDescription}
          toolCount={msg.toolCount}
          duration={msg.duration}
          autoApproved={msg.autoApproved}
        />
      );
    case "tool_chain":
      return msg.toolChain && msg.toolChain.length > 0
        ? <ToolChainDisplay items={msg.toolChain as ToolChainItem[]} />
        : null;
    case "thinking":
      return <ThinkingMessage content={msg.content} />;
    case "status":
      return <StatusMessage content={msg.content} />;
    case "error":
      return <ErrorMessage content={msg.content} />;
    default: {
      const _exhaustive: never = msg.role;
      return _exhaustive;
    }
  }
});
