import type { ReactNode } from "react";
import { SplitBorder } from "../../ui/border.js";

export const TRANSCRIPT_GUTTER_WIDTH = 3;

interface TranscriptRowProps {
  railColor?: string;
  children: ReactNode;
}

export function TranscriptRow({ railColor, children }: TranscriptRowProps) {
  if (railColor) {
    return (
      <box
        flexShrink={0}
        overflow="hidden"
        border={SplitBorder.border}
        borderColor={railColor}
        customBorderChars={SplitBorder.customBorderChars}
      >
        <box flexDirection="column" flexGrow={1} overflow="hidden" paddingLeft={TRANSCRIPT_GUTTER_WIDTH - 1}>
          {children}
        </box>
      </box>
    );
  }

  return (
    <box flexShrink={0} overflow="hidden" paddingLeft={TRANSCRIPT_GUTTER_WIDTH}>
      <box flexDirection="column" flexGrow={1} overflow="hidden">
        {children}
      </box>
    </box>
  );
}
