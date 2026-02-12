import { memo } from "react";
import { colors } from "../../ui/colors.js";
import { Markdown } from "../../Markdown.js";

interface AssistantMessageProps {
  content: string;
  depth?: number;
  renderMarkdown?: boolean;
}

export const AssistantMessage = memo(function AssistantMessage({
  content,
  depth = 0,
  renderMarkdown = true,
}: AssistantMessageProps) {
  return (
    <box paddingLeft={3} flexShrink={0} overflow="hidden">
      <box flexGrow={1} flexDirection="column" overflow="hidden">
        {depth > 0 && (
          <text><span fg={colors.text.disabled}>{"▸".repeat(depth)} depth {depth}</span></text>
        )}
        {renderMarkdown ? (
          <Markdown>{content}</Markdown>
        ) : (
          <text>{content}</text>
        )}
      </box>
    </box>
  );
});
