import { Children, isValidElement, useMemo, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import { Check, Copy } from "lucide-react";
import clsx from "clsx";
import bash from "highlight.js/lib/languages/bash";
import javascript from "highlight.js/lib/languages/javascript";
import json from "highlight.js/lib/languages/json";
import python from "highlight.js/lib/languages/python";
import typescript from "highlight.js/lib/languages/typescript";
import { Mermaid } from "./Mermaid";

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

// rehype-highlight runs first (adds <span class="hljs-…">), then rehype-sanitize.
// We extend the default schema so the highlight spans + classes survive.
const sanitizeSchema = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    code: [...(defaultSchema.attributes?.code ?? []), ["className"]],
    span: [...(defaultSchema.attributes?.span ?? []), ["className"]],
    div: [...(defaultSchema.attributes?.div ?? []), ["className"]],
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
        remarkPlugins={[remarkGfm]}
        rehypePlugins={
          streaming
            ? [[rehypeSanitize, sanitizeSchema]]
            : [
                [rehypeHighlight, { languages: HL_LANGUAGES, detect: false, ignoreMissing: true }],
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
      <div className="code-block-header">
        <span className="code-block-lang">{lang}</span>
        <CopyButton text={rawText} />
      </div>
      <pre>{children}</pre>
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

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
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  };

  return (
    <button
      type="button"
      onClick={() => void onClick()}
      aria-label={copied ? "Copied" : "Copy code"}
      className={clsx("code-block-copy", copied && "copied")}
    >
      {copied ? <Check size={14} strokeWidth={2.4} /> : <Copy size={14} strokeWidth={2} />}
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
