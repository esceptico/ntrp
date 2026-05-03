import { Markdown } from "../../Markdown.js";
import { TranscriptRow } from "./TranscriptRow.js";

interface AssistantMessageProps {
  content: string;
}

export function AssistantMessage({ content }: AssistantMessageProps) {
  return (
    <TranscriptRow>
      <box flexGrow={1} flexDirection="column" overflow="hidden">
        <Markdown>{content}</Markdown>
      </box>
    </TranscriptRow>
  );
}
