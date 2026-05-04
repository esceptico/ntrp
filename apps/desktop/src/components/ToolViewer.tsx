import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Check, Copy, X } from "lucide-react";
import clsx from "clsx";
import { useStore } from "../store";
import { highlight } from "../highlight";

/** Pretty-print JSON; fall back to the raw string when parse fails. The
 *  `lang` field is set to "json" when we successfully reformatted, so the
 *  viewer can syntax-highlight only when we actually have JSON. */
function formatMaybeJson(raw: string | undefined): { body: string; lang: string } {
  if (!raw) return { body: "", lang: "" };
  const trimmed = raw.trim();
  if (!trimmed) return { body: "", lang: "" };
  try {
    return { body: JSON.stringify(JSON.parse(trimmed), null, 2), lang: "json" };
  } catch {
    return { body: raw, lang: "" };
  }
}

export function ToolViewer() {
  const item = useStore((s) => s.viewingTool);
  const close = useStore((s) => s.setViewingTool);

  // Re-read the live item from the store so a streaming result patches in
  // while the viewer is open.
  const live = useStore((s) => {
    if (!item) return null;
    for (const msg of s.messages.values()) {
      if (!msg.activity) continue;
      const found = msg.activity.items.find((it) => it.id === item.id);
      if (found) return found;
    }
    return item;
  });

  const input = useMemo(() => formatMaybeJson(live?.args), [live?.args]);
  const output = useMemo(() => formatMaybeJson(live?.result), [live?.result]);
  const inputHtml = useMemo(
    () => (input.lang ? highlight(input.body, input.lang) : ""),
    [input.body, input.lang],
  );
  const outputHtml = useMemo(
    () => (output.lang ? highlight(output.body, output.lang) : ""),
    [output.body, output.lang],
  );

  useEffect(() => {
    if (!item) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [item, close]);

  if (!item || !live) return null;
  const root = document.querySelector("#app");
  if (!root) return null;

  return createPortal(
    <div
      className="absolute inset-0 z-50 grid place-items-center p-8 bg-[rgba(0,0,0,0.32)] backdrop-blur-md animate-fade-in"
      onClick={() => close(null)}
    >
      <div
        className="w-[min(720px,calc(100vw-80px))] max-w-[min(720px,calc(100vw-80px))] max-h-[calc(100vh-80px)] grid grid-cols-[minmax(0,1fr)] grid-rows-[auto_minmax(0,1fr)] rounded-2xl bg-surface shadow-[var(--shadow-pop)] animate-pop-in overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-start justify-between gap-3.5 px-5 pt-[18px] pb-3 border-b border-line-soft min-w-0">
          <div className="min-w-0 flex-1">
            <div className="text-[16px] font-semibold tracking-[-0.012em] text-ink truncate">
              {live.kind}
            </div>
            {live.target && live.target !== live.kind && (
              <div className="mt-0.5 text-[11.5px] text-faint font-mono truncate">
                {live.target}
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={() => close(null)}
            aria-label="Close"
            className="grid place-items-center w-[26px] h-[26px] rounded-md text-muted hover:bg-surface-soft hover:text-ink transition-colors shrink-0"
          >
            <X size={13} strokeWidth={1.8} />
          </button>
        </header>

        <div className="overflow-y-auto scroll-thin px-5 py-4 grid grid-cols-[minmax(0,1fr)] gap-4 min-w-0">
          <Section
            title="Input"
            body={input.body}
            html={inputHtml}
            placeholder="No input arguments."
          />
          <Section
            title="Output"
            body={output.body}
            html={outputHtml}
            placeholder={live.result == null ? "Waiting for result…" : "Empty result."}
          />
        </div>
      </div>
    </div>,
    root,
  );
}

function Section({
  title,
  body,
  html,
  placeholder,
}: {
  title: string;
  body: string;
  html: string;
  placeholder: string;
}) {
  const [copied, setCopied] = useState(false);
  const hasBody = body.trim().length > 0;

  const onCopy = async () => {
    if (!hasBody) return;
    try {
      await navigator.clipboard.writeText(body);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      /* clipboard refused — silently ignore */
    }
  };

  return (
    <section className="grid grid-cols-[minmax(0,1fr)] gap-1.5 min-w-0">
      <div className="flex items-center gap-2">
        <h3 className="m-0 text-[10.5px] font-medium uppercase tracking-[0.08em] text-faint">
          {title}
        </h3>
        {hasBody && (
          <button
            type="button"
            onClick={() => void onCopy()}
            aria-label={copied ? "Copied" : "Copy"}
            className={clsx(
              "ml-auto inline-flex items-center gap-1 h-6 px-1.5 rounded-md text-[11px] font-medium tracking-[-0.005em] transition-colors",
              copied
                ? "text-accent-strong bg-accent-soft"
                : "text-muted hover:bg-surface-soft hover:text-ink",
            )}
          >
            {copied ? <Check size={11} strokeWidth={2.4} /> : <Copy size={11} strokeWidth={1.8} />}
            {copied ? "Copied" : "Copy"}
          </button>
        )}
      </div>
      {hasBody ? (
        html ? (
          <pre
            className="hljs m-0 p-3 rounded-[10px] bg-code-bg border border-line-soft text-[12.25px] leading-[1.55] text-ink-soft font-mono whitespace-pre-wrap break-all max-h-[40vh] min-w-0 max-w-full overflow-y-auto overflow-x-hidden scroll-thin"
            dangerouslySetInnerHTML={{ __html: html }}
          />
        ) : (
          <pre className="m-0 p-3 rounded-[10px] bg-code-bg border border-line-soft text-[12.25px] leading-[1.55] text-ink-soft font-mono whitespace-pre-wrap break-all max-h-[40vh] min-w-0 max-w-full overflow-y-auto overflow-x-hidden scroll-thin">
            {body}
          </pre>
        )
      ) : (
        <div className="px-3 py-2.5 rounded-[10px] bg-surface-soft text-[12.5px] text-faint italic">
          {placeholder}
        </div>
      )}
    </section>
  );
}
