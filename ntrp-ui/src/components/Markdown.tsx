import { useMemo } from "react";
import { RGBA, SyntaxStyle } from "@opentui/core";
import { colors } from "./ui/colors.js";

interface MarkdownProps {
  children: string;
  dimmed?: boolean;
}

export function Markdown({ children, dimmed }: MarkdownProps) {
  const content = children.trim();

  const syntaxStyle = useMemo(
    () => SyntaxStyle.fromStyles({
      default: { fg: RGBA.fromHex(dimmed ? colors.text.muted : colors.text.primary) },
    }),
    [dimmed, colors.text.primary, colors.text.muted]
  );

  if (!content) return null;

  return <markdown content={content} syntaxStyle={syntaxStyle} />;
}
