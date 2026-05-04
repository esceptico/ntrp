import { useEffect, useRef } from "react";
import clsx from "clsx";

const CHECK_ICON_SVG =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" width="13" height="13" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>';

const COPY_ICON_SVG =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="13" height="13" aria-hidden="true"><rect width="14" height="14" x="8" y="8" rx="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>';

async function writeToClipboard(text: string): Promise<boolean> {
  // Async Clipboard API. Works in Electron secure contexts.
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      /* fall through to legacy path */
    }
  }
  // Legacy fallback via a hidden textarea + execCommand("copy"). Some
  // environments (older Electron, restrictive CSP) reject the async API
  // even from a click handler.
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}

/** Renders pre-sanitized markdown HTML and wires up the copy buttons that
 *  `renderMarkdown` injects into fenced code blocks. We bind handlers
 *  directly on each `.code-block-copy` button (instead of delegating from
 *  the root) so the click works across streaming re-renders that swap the
 *  inner DOM. */
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
    const buttons = Array.from(
      root.querySelectorAll<HTMLButtonElement>("button.code-block-copy"),
    );
    const cleanup: Array<() => void> = [];

    for (const button of buttons) {
      const onClick = async (e: Event) => {
        e.preventDefault();
        e.stopPropagation();
        const encoded = button.dataset.code ?? "";
        let code: string;
        try {
          code = decodeURIComponent(encoded);
        } catch {
          code = encoded;
        }
        const ok = await writeToClipboard(code);
        if (!ok) return;
        button.classList.add("copied");
        button.innerHTML = CHECK_ICON_SVG;
        window.setTimeout(() => {
          button.classList.remove("copied");
          button.innerHTML = COPY_ICON_SVG;
        }, 1200);
      };
      button.addEventListener("click", onClick);
      cleanup.push(() => button.removeEventListener("click", onClick));
    }

    return () => {
      for (const fn of cleanup) fn();
    };
  }, [html]);

  return (
    <div
      ref={ref}
      className={clsx("md", className)}
      dangerouslySetInnerHTML={{ __html: html || "&nbsp;" }}
    />
  );
}
