import { useMemo } from "react";
import { RGBA, SyntaxStyle } from "@opentui/core";
import { colors, currentAccent, useThemeVersion } from "./ui/colors.js";

interface MarkdownProps {
  children: string;
  dimmed?: boolean;
  streaming?: boolean;
}

function buildSyntaxStyle(dimmed: boolean) {
  const fg = dimmed ? colors.text.muted : colors.text.primary;
  const secondary = colors.text.secondary;
  const muted = colors.text.muted;
  const accent = currentAccent.primary;

  return SyntaxStyle.fromStyles({
    default: { fg: RGBA.fromHex(fg) },

    // Headings
    "markup.heading.1": { fg: RGBA.fromHex(accent), bold: true },
    "markup.heading.2": { fg: RGBA.fromHex(accent), bold: true },
    "markup.heading.3": { fg: RGBA.fromHex(accent), bold: true },
    "markup.heading.4": { fg: RGBA.fromHex(accent) },
    "markup.heading.5": { fg: RGBA.fromHex(accent) },
    "markup.heading.6": { fg: RGBA.fromHex(accent) },
    "markup.heading": { fg: RGBA.fromHex(accent), bold: true },

    // Inline
    "markup.strong": { fg: RGBA.fromHex(fg), bold: true },
    "markup.italic": { fg: RGBA.fromHex(fg), italic: true },
    "markup.strikethrough": { fg: RGBA.fromHex(muted), dim: true },
    "markup.raw": { fg: RGBA.fromHex(secondary) },
    "markup.raw.block": { fg: RGBA.fromHex(secondary) },

    // Links
    "markup.link": { fg: RGBA.fromHex(accent), underline: true },
    "markup.link.url": { fg: RGBA.fromHex(muted), underline: true },
    "markup.link.label": { fg: RGBA.fromHex(accent) },

    // Lists & quotes
    "markup.list": { fg: RGBA.fromHex(muted) },
    "markup.list.checked": { fg: RGBA.fromHex(colors.status.success) },
    "markup.list.unchecked": { fg: RGBA.fromHex(muted) },
    "markup.quote": { fg: RGBA.fromHex(muted), italic: true },

    // Punctuation & misc
    "punctuation.special": { fg: RGBA.fromHex(muted), dim: true },
    "punctuation.delimiter": { fg: RGBA.fromHex(muted) },
    "label": { fg: RGBA.fromHex(muted), dim: true },
    "conceal": { fg: RGBA.fromHex(muted) },
    "string.escape": { fg: RGBA.fromHex(secondary) },
  });
}

export function Markdown({ children, dimmed, streaming }: MarkdownProps) {
  const content = children.trim();
  const tv = useThemeVersion();

  const syntaxStyle = useMemo(
    () => buildSyntaxStyle(dimmed ?? false),
    [dimmed, tv]
  );

  if (!content) return null;

  return (
    <markdown
      content={content}
      syntaxStyle={syntaxStyle}
      conceal
      streaming={streaming}
    />
  );
}
