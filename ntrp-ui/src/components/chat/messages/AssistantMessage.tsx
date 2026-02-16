import { Markdown } from "../../Markdown.js";

interface AssistantMessageProps {
  content: string;
}

export function AssistantMessage({ content }: AssistantMessageProps) {
  return (
    <box paddingLeft={3} flexShrink={0} overflow="hidden">
      <box flexGrow={1} flexDirection="column" overflow="hidden">
        <Markdown>{content}</Markdown>
      </box>
    </box>
  );
}
