import { memo } from "react";
import { useAccentColor } from "../../../hooks/index.js";
import { colors } from "../../ui/colors.js";
import { SplitBorder } from "../../ui/border.js";

interface UserMessageProps {
  content: string;
}

export const UserMessage = memo(function UserMessage({ content }: UserMessageProps) {
  const { accentValue } = useAccentColor();

  return (
    <box
      overflow="hidden"
      border={SplitBorder.border}
      borderColor={accentValue}
      customBorderChars={SplitBorder.customBorderChars}
    >
      <box
        paddingTop={1}
        paddingBottom={1}
        paddingLeft={2}
        paddingRight={2}
        backgroundColor={colors.background.panel}
        flexShrink={0}
      >
        <text fg={colors.text.primary}>{content}</text>
      </box>
    </box>
  );
});
