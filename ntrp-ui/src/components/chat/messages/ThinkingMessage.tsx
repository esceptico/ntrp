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
      overflow="hidden"
      border={SplitBorder.border}
      borderColor={colors.background.element ?? colors.border}
      customBorderChars={SplitBorder.customBorderChars}
    >
      <box flexDirection="column" overflow="hidden" paddingLeft={2} paddingRight={2}>
        <text>
          <span fg={accentValue}>Reasoning</span>
        </text>
        {content && (
          <box overflow="hidden">
            <text><span fg={colors.text.secondary}>{content.trimStart()}</span></text>
          </box>
        )}
      </box>
    </box>
  );
});
