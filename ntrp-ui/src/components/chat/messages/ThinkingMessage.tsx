import { memo } from "react";
import { colors } from "../../ui/colors.js";
import { useAccentColor } from "../../../hooks/index.js";
import { SplitBorder } from "../../ui/border.js";

interface ThinkingMessageProps {
  content: string;
}

export const ThinkingMessage = memo(function ThinkingMessage({ content }: ThinkingMessageProps) {
  const { accentValue } = useAccentColor();

  return (
    <box
      flexDirection="column"
      overflow="hidden"
      border={SplitBorder.border}
      borderColor={colors.background.element}
      customBorderChars={SplitBorder.customBorderChars}
      paddingLeft={2}
    >
      <text>
        <span fg={accentValue}>Thinking{"\u2026"}</span>
      </text>
      {content && (
        <box overflow="hidden">
          <text><span fg={colors.text.secondary}>{content}</span></text>
        </box>
      )}
    </box>
  );
});
