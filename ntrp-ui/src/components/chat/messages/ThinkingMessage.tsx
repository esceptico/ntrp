import { memo } from "react";
import { colors } from "../../ui/colors.js";
import { useAccentColor } from "../../../hooks/index.js";
import { TranscriptRow } from "./TranscriptRow.js";

interface ThinkingMessageProps {
  content: string;
}

export const ThinkingMessage = memo(function ThinkingMessage({ content }: ThinkingMessageProps) {
  const { accentValue } = useAccentColor();

  return (
    <TranscriptRow railColor={colors.background.element ?? colors.border}>
      <text>
        <span fg={accentValue}>Reasoning</span>
      </text>
      {content && (
        <box overflow="hidden">
          <text><span fg={colors.text.secondary}>{content.trimStart()}</span></text>
        </box>
      )}
    </TranscriptRow>
  );
});
