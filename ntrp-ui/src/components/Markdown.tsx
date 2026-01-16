import React, { memo, useMemo } from "react";
import { Text } from "ink";
import markdownToCli from "cli-markdown";

interface MarkdownProps {
  children: string;
  dimmed?: boolean;
}

// Use cli-markdown for proper terminal markdown rendering
export const Markdown = memo(function Markdown({ children, dimmed }: MarkdownProps) {
  const rendered = useMemo(() => {
    try {
      const output = markdownToCli(children);
      if (typeof output !== "string") return "";
      // Strip trailing newlines and ANSI reset codes
      return output.replace(/(\r?\n|\x1b\[0m)+$/g, "").trim();
    } catch {
      return children;
    }
  }, [children]);

  return <Text dimColor={dimmed}>{rendered}</Text>;
});
