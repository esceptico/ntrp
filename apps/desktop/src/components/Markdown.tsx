import { Children, isValidElement, useMemo, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeHighlight from "rehype-highlight";
import rehypeKatex from "rehype-katex";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import { Check, Copy } from "lucide-react";
import clsx from "clsx";
import bash from "highlight.js/lib/languages/bash";
import javascript from "highlight.js/lib/languages/javascript";
import json from "highlight.js/lib/languages/json";
import python from "highlight.js/lib/languages/python";
import typescript from "highlight.js/lib/languages/typescript";
import { Mermaid } from "./Mermaid";
import { ICON } from "../lib/icons";
import { useTimeoutFlag } from "../lib/hooks";

const HL_LANGUAGES = {
  json,
  python,
  py: python,
  javascript,
  js: javascript,
  jsx: javascript,
  typescript,
  ts: typescript,
  tsx: typescript,
  bash,
  sh: bash,
  shell: bash,
  zsh: bash,
};

// rehype-highlight and rehype-katex both inject elements with classes;
// rehype-sanitize runs last to strip anything we don't whitelist. The
// schema below preserves:
//   - <span class="hljs-…"> from rehype-highlight
//   - <span class="katex…">, <math>, <mrow>, <mi>, etc. from rehype-katex
//   - inline `style` on KaTeX spans (used for character spacing / sizing)
//   - the standard math attributes MathML output needs
const MATH_TAGS = [
  "math", "annotation", "semantics",
  "mrow", "mi", "mo", "mn", "ms", "mtext", "mspace",
  "msup", "msub", "msubsup", "mfrac", "mroot", "msqrt",
  "mtable", "mtr", "mtd", "munder", "mover", "munderover",
  "menclose", "mphantom", "mpadded", "mfenced",
] as const;

const sanitizeSchema = {
  ...defaultSchema,
  tagNames: [...(defaultSchema.tagNames ?? []), ...MATH_TAGS],
  attributes: {
    ...defaultSchema.attributes,
    code: [...(defaultSchema.attributes?.code ?? []), ["className"]],
    span: [...(defaultSchema.attributes?.span ?? []), ["className"], "style"],
    div: [...(defaultSchema.attributes?.div ?? []), ["className"], "style"],
    // KaTeX uses MathML annotations and explicit display modes.
    math: [["xmlns"], "display"],
    annotation: [["encoding"]],
    // Most MathML presentation elements carry a `mathvariant` and/or
    // `displaystyle` — keep the common set so semantic rendering works.
    mi: [["mathvariant"]],
    mo: [["fence"], "lspace", "rspace", "stretchy"],
    mn: [],
    mfrac: [["linethickness"]],
    mtable: [["columnalign"], "rowspacing", "columnspacing"],
    mtd: [["columnalign"]],
  },
};

export function Markdown({
  content,
  className,
  streaming = false,
}: {
  content: string;
  className?: string;
  streaming?: boolean;
}) {
  return (
    <div className={clsx("md", className)}>
      <ReactMarkdown
        // remark-math parses $...$ (inline) and $$...$$ (display) into
        // math nodes; rehype-katex converts those into the spans/MathML
        // KaTeX needs for rendering. The order matters — katex MUST run
        // before sanitize so its output exists when sanitize walks the
        // tree, but the sanitize schema is extended above to keep the
        // tags/classes/attributes katex emits.
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={
          streaming
            ? [
                // During streaming we skip rehype-highlight (it's CPU-heavy
                // on partial content), but math still renders fine — katex
                // tolerates incomplete `$$` blocks by leaving them as text
                // until both delimiters are present.
                [rehypeKatex, { strict: false, throwOnError: false }],
                [rehypeSanitize, sanitizeSchema],
              ]
            : [
                [rehypeHighlight, { languages: HL_LANGUAGES, detect: false, ignoreMissing: true }],
                [rehypeKatex, { strict: false, throwOnError: false }],
                [rehypeSanitize, sanitizeSchema],
              ]
        }
        components={{ pre: streaming ? StreamingPreBlock : PreBlock, a: Anchor }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

function Anchor({ href, children, ...rest }: React.AnchorHTMLAttributes<HTMLAnchorElement>) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" {...rest}>
      {children}
    </a>
  );
}

function StreamingPreBlock({ children }: { children?: ReactNode }) {
  return <pre className="streaming-code">{children}</pre>;
}

/** Custom <pre> wrapper: pulls language + raw text from the inner <code>
 *  child and renders our header (language label + copy button) above the
 *  highlighted code. */
function PreBlock({ children }: { children?: ReactNode }) {
  // ReactMarkdown gives us a single <code> element child — extract its
  // className (carries the language) and the raw text before highlighting.
  const codeNode = Children.toArray(children).find(
    (child): child is React.ReactElement<{ className?: string; children?: ReactNode }> =>
      isValidElement(child) && (child as { type?: unknown }).type === "code",
  );
  const className = codeNode?.props.className ?? "";
  const lang = className.match(/(?:^|\s)language-(\S+)/)?.[1] ?? "";
  const rawText = useMemo(() => extractText(codeNode?.props.children), [codeNode]);

  if (lang === "mermaid" && rawText.trim()) {
    return <Mermaid code={rawText} />;
  }

  return (
    <div className="code-block">
      <span className="code-block-tick code-block-tick--tl" aria-hidden="true" />
      <span className="code-block-tick code-block-tick--tr" aria-hidden="true" />
      <div className="code-block-header">
        <span className="code-block-lang">{lang}</span>
        <CopyButton text={rawText} />
      </div>
      <pre>{children}</pre>
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, flashCopied] = useTimeoutFlag(1200);

  const onClick = async () => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // Fallback for restrictive contexts (some Electron builds lock the
      // navigator.clipboard write API behind permissions): use the legacy
      // execCommand path.
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand("copy");
      } finally {
        document.body.removeChild(ta);
      }
    }
    flashCopied();
  };

  return (
    <button
      type="button"
      onClick={() => void onClick()}
      aria-label={copied ? "Copied" : "Copy code"}
      className={clsx("code-block-copy", copied && "copied")}
    >
      {copied ? <Check size={ICON.SM} strokeWidth={2.4} /> : <Copy size={ICON.SM} strokeWidth={2} />}
    </button>
  );
}

function extractText(node: ReactNode): string {
  if (node == null || node === false) return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(extractText).join("");
  if (isValidElement(node)) {
    const children = (node as React.ReactElement<{ children?: ReactNode }>).props.children;
    return extractText(children);
  }
  return "";
}
