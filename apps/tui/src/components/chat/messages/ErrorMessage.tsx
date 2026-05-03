import { memo } from "react";
import { colors, useThemeVersion } from "../../ui/colors.js";
import { TranscriptRow } from "./TranscriptRow.js";

interface ErrorMessageProps {
  content: string;
}

export const ErrorMessage = memo(function ErrorMessage({ content }: ErrorMessageProps) {
  useThemeVersion();

  return (
    <TranscriptRow railColor={colors.status.error}>
      <box
        paddingTop={1}
        paddingBottom={1}
        paddingRight={2}
        backgroundColor={colors.background.panel}
        overflow="hidden"
      >
        <text><span fg={colors.status.error}>{content}</span></text>
      </box>
    </TranscriptRow>
  );
});
