import { memo } from "react";
import { colors, useThemeVersion } from "../../ui/colors.js";
import { useDimensions } from "../../../contexts/index.js";
import { truncateText } from "../../ui/index.js";
import { TranscriptRow, TRANSCRIPT_GUTTER_WIDTH } from "./TranscriptRow.js";

interface StatusMessageProps {
  content: string;
}

export const StatusMessage = memo(function StatusMessage({ content }: StatusMessageProps) {
  useThemeVersion();
  const { width } = useDimensions();
  const contentWidth = Math.max(0, width - TRANSCRIPT_GUTTER_WIDTH);

  return (
    <TranscriptRow>
      <text>
        <span fg={colors.text.muted}><em>{truncateText(content, contentWidth)}</em></span>
      </text>
    </TranscriptRow>
  );
});
