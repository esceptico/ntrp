import { memo } from "react";
import { colors, useThemeVersion } from "../../ui/colors.js";
import { SplitBorder } from "../../ui/border.js";

interface ErrorMessageProps {
  content: string;
}

export const ErrorMessage = memo(function ErrorMessage({ content }: ErrorMessageProps) {
  useThemeVersion();

  return (
    <box
      overflow="hidden"
      border={SplitBorder.border}
      borderColor={colors.status.error}
      customBorderChars={SplitBorder.customBorderChars}
    >
      <box
        paddingTop={1}
        paddingBottom={1}
        paddingLeft={2}
        paddingRight={2}
        backgroundColor={colors.background.panel}
      >
        <text><span fg={colors.status.error}>{content}</span></text>
      </box>
    </box>
  );
});
