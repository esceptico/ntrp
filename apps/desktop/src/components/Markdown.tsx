import type { JSX } from "react";
import { Streamdown, type ExtraProps } from "streamdown";
import clsx from "clsx";

// Streamdown is Vercel's drop-in react-markdown replacement built for LLM
// token streams. It stabilizes incomplete markdown blocks (half-written code
// fences, unterminated bold/links) and ships GFM, Shiki syntax highlighting +
// copy buttons, Mermaid, and KaTeX math out of the box. The Tailwind classes
// it emits are pulled into the build via the `@source` directive in
// styles.css; KaTeX CSS is imported there too.

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
      <Streamdown
        mode={streaming ? "streaming" : "static"}
        lineNumbers={false}
        components={{ a: Anchor }}
      >
        {content}
      </Streamdown>
    </div>
  );
}

// Open links in a new tab, matching the previous react-markdown behavior.
// Streamdown passes the hast `node` alongside the standard anchor props; we
// drop it so it doesn't land on the DOM element.
function Anchor({ href, children, node: _node, ...rest }: JSX.IntrinsicElements["a"] & ExtraProps) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" {...rest}>
      {children}
    </a>
  );
}
