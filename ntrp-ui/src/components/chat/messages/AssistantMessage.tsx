import { memo } from "react";
import { Markdown } from "../../Markdown.js";

interface AssistantMessageProps {
  content: string;
  renderMarkdown?: boolean;
}

export const AssistantMessage = memo(function AssistantMessage({
  content,
  renderMarkdown = true,
}: AssistantMessageProps) {
  return (
    <box paddingLeft={3} flexShrink={0} overflow="hidden">
      <box flexGrow={1} flexDirection="column" overflow="hidden">
        {renderMarkdown ? (
          <Markdown>{content}</Markdown>
        ) : (
          <text>{content}</text>
        )}
      </box>
    </box>
  );
});
