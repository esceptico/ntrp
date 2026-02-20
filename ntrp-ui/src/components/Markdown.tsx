import { useMemo } from "react";
import { RGBA, SyntaxStyle } from "@opentui/core";
import { colors, useThemeVersion } from "./ui/colors.js";

interface MarkdownProps {
  children: string;
  dimmed?: boolean;
}

export function Markdown({ children, dimmed }: MarkdownProps) {
  const content = children.trim();
  const tv = useThemeVersion();

  const syntaxStyle = useMemo(
    () => SyntaxStyle.fromStyles({
      default: { fg: RGBA.fromHex(dimmed ? colors.text.muted : colors.text.primary) },
    }),
    [dimmed, tv]
  );

  if (!content) return null;

  return <markdown content={content} syntaxStyle={syntaxStyle} />;
}
