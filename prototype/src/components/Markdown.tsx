import { memo } from "react";
import { RGBA, SyntaxStyle } from "@opentui/core";
import { colors } from "./ui/colors.js";

const defaultSyntaxStyle = SyntaxStyle.fromStyles({
  default: { fg: RGBA.fromHex(colors.text.primary) },
});

const dimmedSyntaxStyle = SyntaxStyle.fromStyles({
  default: { fg: RGBA.fromHex(colors.text.muted) },
});

interface MarkdownProps {
  children: string;
  dimmed?: boolean;
}

export const Markdown = memo(function Markdown({ children, dimmed }: MarkdownProps) {
  const content = children.trim();
  if (!content) return null;

  return (
    <markdown
      content={content}
      syntaxStyle={dimmed ? dimmedSyntaxStyle : defaultSyntaxStyle}
    />
  );
});
