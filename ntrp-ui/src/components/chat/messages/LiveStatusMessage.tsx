import { memo } from "react";
import { Status, type Status as StatusType } from "../../../lib/constants.js";
import { useAccentColor } from "../../../hooks/index.js";
import { colors } from "../../ui/colors.js";
import { BrailleCompress, BraillePendulum, CyclingStatus } from "../../ui/spinners/index.js";
import { TranscriptRow } from "./TranscriptRow.js";

interface LiveStatusMessageProps {
  isStreaming: boolean;
  status: StatusType;
}

export const LiveStatusMessage = memo(function LiveStatusMessage({
  isStreaming,
  status,
}: LiveStatusMessageProps) {
  const { accentValue } = useAccentColor();
  const compressing = status === Status.COMPRESSING;

  return (
    <TranscriptRow railColor={colors.background.element ?? colors.border}>
      <box flexDirection="row" gap={1} overflow="hidden">
        <box width={8} flexShrink={0}>
          {compressing ? (
            <BrailleCompress width={8} color={accentValue} interval={30} />
          ) : (
            <BraillePendulum width={8} color={accentValue} spread={1} interval={20} />
          )}
        </box>
        {compressing ? (
          <text><span fg={colors.text.muted}>compressing context</span></text>
        ) : (
          <CyclingStatus status={status} isStreaming={isStreaming} />
        )}
        {isStreaming && (
          <text>
            <span fg={colors.text.disabled}> · </span>
            <span fg={colors.footer}>esc</span>
            <span fg={colors.text.disabled}> interrupt · </span>
            <span fg={colors.footer}>ctrl+o</span>
            <span fg={colors.text.disabled}> background</span>
          </text>
        )}
      </box>
    </TranscriptRow>
  );
});
