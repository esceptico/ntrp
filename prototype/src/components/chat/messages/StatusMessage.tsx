import { memo } from "react";
import { colors } from "../../ui/colors.js";
import { useDimensions } from "../../../contexts/index.js";
import { truncateText } from "../../ui/index.js";

interface StatusMessageProps {
  content: string;
}

export const StatusMessage = memo(function StatusMessage({ content }: StatusMessageProps) {
  const { width: terminalWidth } = useDimensions();
  const contentWidth = Math.max(0, terminalWidth - 4);

  return (
    <box paddingLeft={3} width={contentWidth} overflow="hidden">
      <text>
        <span fg={colors.text.muted}><em>{truncateText(content, contentWidth)}</em></span>
      </text>
    </box>
  );
});
