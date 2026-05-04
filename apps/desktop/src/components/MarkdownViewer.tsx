import { useEffect, useMemo } from "react";
import { createPortal } from "react-dom";
import { ExternalLink, X } from "lucide-react";
import { useStore } from "../store";
import { renderMarkdown } from "../markdown";
import { MarkdownContent } from "./MarkdownContent";

/** Generic markdown viewer modal. State lives in the store as `viewingMarkdown`
 *  so any code can pop the viewer with a `setViewingMarkdown({title, content, ...})`
 *  call. Used today for skill files; reusable for memory notes, project docs,
 *  anything else that's markdown. */
export function MarkdownViewer() {
  const view = useStore((s) => s.viewingMarkdown);
  const close = useStore((s) => s.setViewingMarkdown);

  const html = useMemo(() => (view ? renderMarkdown(view.content) : ""), [view?.content]);

  useEffect(() => {
    if (!view) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [view, close]);

  if (!view) return null;

  const root = document.querySelector("#app");
  if (!root) return null;

  const openExternal = () => {
    if (view.sourcePath) void window.ntrpDesktop?.shell?.openPath(view.sourcePath);
  };

  return createPortal(
    <div
      className="absolute inset-0 z-50 grid place-items-center p-8 bg-[rgba(28,26,22,0.32)] backdrop-blur-md animate-fade-in"
      onClick={() => close(null)}
    >
      <div
        className="w-[min(720px,calc(100vw-80px))] max-h-[calc(100vh-80px)] grid grid-rows-[auto_minmax(0,1fr)] rounded-2xl bg-surface shadow-[var(--shadow-pop)] animate-pop-in overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-start justify-between gap-3.5 px-5 pt-[18px] pb-3 border-b border-line-soft">
          <div className="min-w-0">
            <div className="text-[16px] font-semibold tracking-[-0.012em] text-ink truncate">
              {view.title}
            </div>
            {view.subtitle && (
              <div className="mt-0.5 text-[11.5px] text-faint font-mono truncate">
                {view.subtitle}
              </div>
            )}
          </div>
          <div className="flex items-center gap-1 shrink-0">
            {view.sourcePath && (
              <button
                type="button"
                onClick={openExternal}
                aria-label="Open in default app"
                title="Open in default app"
                className="grid place-items-center w-[26px] h-[26px] rounded-md text-muted hover:bg-surface-soft hover:text-ink transition-colors"
              >
                <ExternalLink size={13} strokeWidth={1.8} />
              </button>
            )}
            <button
              type="button"
              onClick={() => close(null)}
              aria-label="Close"
              className="grid place-items-center w-[26px] h-[26px] rounded-md text-muted hover:bg-surface-soft hover:text-ink transition-colors"
            >
              <X size={13} strokeWidth={1.8} />
            </button>
          </div>
        </header>
        <div className="overflow-y-auto scroll-thin px-5 py-4">
          <MarkdownContent html={html} className="text-[14px] leading-[1.6] text-ink" />
        </div>
      </div>
    </div>,
    root,
  );
}
