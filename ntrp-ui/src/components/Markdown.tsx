import { useEffect, useRef, useState } from "react";
import { RGBA, SyntaxStyle } from "@opentui/core";
import { colors, currentAccent, useThemeVersion } from "./ui/colors.js";

interface MarkdownProps {
  children: string;
  dimmed?: boolean;
  streaming?: boolean;
}

function hex(c: string) { return RGBA.fromHex(c); }

function buildSyntaxStyle(dimmed: boolean) {
  const fg = dimmed ? colors.text.muted : colors.text.primary;
  const secondary = colors.text.secondary;
  const muted = colors.text.muted;
  const disabled = colors.text.disabled;
  const accent = currentAccent.primary;
  const shimmer = currentAccent.shimmer;
  const { success, error, warning, processing } = colors.status;
  const elementBg = colors.background.element;

  return SyntaxStyle.fromStyles({
    default: { fg: hex(fg) },

    // -- Headings --
    "markup.heading.1": { fg: hex(accent), bold: true },
    "markup.heading.2": { fg: hex(accent), bold: true },
    "markup.heading.3": { fg: hex(accent) },
    "markup.heading.4": { fg: hex(secondary), bold: true },
    "markup.heading.5": { fg: hex(secondary) },
    "markup.heading.6": { fg: hex(muted) },
    "markup.heading": { fg: hex(accent), bold: true },

    // -- Inline formatting --
    "markup.strong": { fg: hex(fg), bold: true },
    "markup.italic": { fg: hex(fg), italic: true },
    "markup.strikethrough": { fg: hex(muted), dim: true },
    "markup.raw": { fg: hex(secondary), bg: elementBg ? hex(elementBg) : undefined },
    "markup.raw.block": { fg: hex(fg), bg: elementBg ? hex(elementBg) : undefined },

    // -- Links --
    "markup.link": { fg: hex(muted), dim: true },
    "markup.link.label": { fg: hex(accent), underline: true },
    "markup.link.url": { fg: hex(disabled), dim: true },

    // -- Lists & quotes --
    "markup.list": { fg: hex(muted) },
    "markup.list.checked": { fg: hex(success) },
    "markup.list.unchecked": { fg: hex(muted) },
    "markup.quote": { fg: hex(muted), italic: true },

    // -- Punctuation & meta --
    "punctuation.special": { fg: hex(muted), dim: true },
    "punctuation.delimiter": { fg: hex(muted) },
    "punctuation.bracket": { fg: hex(muted) },
    "label": { fg: hex(muted), dim: true },
    "conceal": { fg: hex(disabled) },

    // -- Code: keywords --
    "keyword": { fg: hex(processing), bold: true },
    "keyword.conditional": { fg: hex(processing), bold: true },
    "keyword.return": { fg: hex(processing), bold: true },
    "keyword.exception": { fg: hex(processing), bold: true },
    "keyword.import": { fg: hex(processing) },
    "keyword.function": { fg: hex(processing) },
    "keyword.type": { fg: hex(processing) },
    "keyword.modifier": { fg: hex(processing) },
    "keyword.operator": { fg: hex(secondary) },
    "keyword.directive": { fg: hex(muted) },
    "keyword.coroutine": { fg: hex(processing) },

    // -- Code: functions --
    "function": { fg: hex(accent) },
    "function.method": { fg: hex(accent) },
    "function.call": { fg: hex(accent) },
    "function.method.call": { fg: hex(accent) },
    "function.builtin": { fg: hex(accent) },

    // -- Code: types --
    "type": { fg: hex(warning) },
    "type.builtin": { fg: hex(warning) },
    "constructor": { fg: hex(warning) },

    // -- Code: strings & literals --
    "string": { fg: hex(success) },
    "string.escape": { fg: hex(warning) },
    "string.regexp": { fg: hex(error) },
    "string.special": { fg: hex(success) },
    "string.special.url": { fg: hex(accent), underline: true },
    "string.special.key": { fg: hex(accent) },
    "number": { fg: hex(shimmer) },
    "boolean": { fg: hex(shimmer) },
    "constant": { fg: hex(shimmer) },
    "constant.builtin": { fg: hex(shimmer) },

    // -- Code: variables --
    "variable": { fg: hex(fg) },
    "variable.member": { fg: hex(fg) },
    "variable.parameter": { fg: hex(fg), italic: true },
    "variable.builtin": { fg: hex(error) },

    // -- Code: comments --
    "comment": { fg: hex(muted), italic: true },
    "comment.documentation": { fg: hex(muted), italic: true },

    // -- Code: misc --
    "operator": { fg: hex(secondary) },
    "property": { fg: hex(fg) },
    "attribute": { fg: hex(warning), italic: true },
    "escape": { fg: hex(warning) },
    "module": { fg: hex(secondary) },
    "module.builtin": { fg: hex(secondary) },
    "embedded": { fg: hex(fg) },
  });
}

export function Markdown({ children, dimmed, streaming }: MarkdownProps) {
  const content = children.trim();
  const tv = useThemeVersion();

  const [syntaxStyle, setSyntaxStyle] = useState(() => buildSyntaxStyle(dimmed ?? false));
  const prevRef = useRef(syntaxStyle);

  useEffect(() => {
    const next = buildSyntaxStyle(dimmed ?? false);
    const prev = prevRef.current;
    prevRef.current = next;
    setSyntaxStyle(next);
    return () => { prev.destroy(); };
  }, [dimmed, tv]);

  // OpenTUI's CodeRenderable defaults its text buffer fg to white, which
  // leaks through for unstyled code (no filetype, tree-sitter miss, etc.)
  // and renders invisibly on light themes. Override via renderNode.
  const codeFg = dimmed ? colors.text.muted : colors.text.primary;
  const renderNode = (token: { type: string }, context: { defaultRender: () => unknown }) => {
    if (token.type !== "code") return null;
    const renderable = context.defaultRender() as { fg?: unknown } | null;
    if (renderable) renderable.fg = hex(codeFg);
    return renderable as never;
  };

  if (!content) return null;

  return (
    <markdown
      content={content}
      syntaxStyle={syntaxStyle}
      conceal
      streaming={streaming}
      renderNode={renderNode}
    />
  );
}
