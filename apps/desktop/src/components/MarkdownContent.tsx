import { useEffect, useRef } from "react";
import clsx from "clsx";

const CHECK_ICON_SVG =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" width="13" height="13" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>';

const COPY_ICON_SVG =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="13" height="13" aria-hidden="true"><rect width="14" height="14" x="8" y="8" rx="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>';

/** Renders pre-sanitized HTML and wires copy buttons inside fenced code
 *  blocks. The button DOM is created in `renderMarkdown()` (see
 *  `wrapCodeBlocks`); this component takes care of the click delegation
 *  + temporary "copied" feedback. */
export function MarkdownContent({
  html,
  className,
}: {
  html: string;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const root = ref.current;
    if (!root) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as HTMLElement | null;
      const button = target?.closest<HTMLButtonElement>("button.code-block-copy");
      if (!button) return;
      e.preventDefault();
      const encoded = button.dataset.code ?? "";
      let code = "";
      try {
        code = decodeURIComponent(encoded);
      } catch {
        code = encoded;
      }
      void navigator.clipboard.writeText(code).then(() => {
        button.classList.add("copied");
        button.innerHTML = CHECK_ICON_SVG;
        window.setTimeout(() => {
          button.classList.remove("copied");
          button.innerHTML = COPY_ICON_SVG;
        }, 1200);
      });
    };
    root.addEventListener("click", handler);
    return () => root.removeEventListener("click", handler);
  }, []);

  return (
    <div
      ref={ref}
      className={clsx("md", className)}
      dangerouslySetInnerHTML={{ __html: html || "&nbsp;" }}
    />
  );
}
