import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Maximize2, Minus, Plus, RotateCcw, X } from "lucide-react";

/** Pull the current value of a CSS custom property from :root. Read each time
 *  Mermaid initializes so theme switches between light and dark are picked up. */
function tok(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

let initPromise: Promise<typeof import("mermaid").default> | null = null;
let initializedTheme: "light" | "dark" | null = null;

function currentTheme(): "light" | "dark" {
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** Lazy-load mermaid on first use; re-initialise when the OS theme flips so
 *  freshly-rendered diagrams pick up the new palette. */
async function getMermaid(): Promise<typeof import("mermaid").default> {
  if (!initPromise) {
    initPromise = import("mermaid").then((m) => m.default);
  }
  const mermaid = await initPromise;
  const theme = currentTheme();
  if (initializedTheme !== theme) {
    const ink = tok("--color-ink");
    const ink_soft = tok("--color-ink-soft");
    const muted = tok("--color-muted");
    const faint = tok("--color-faint");
    const line = tok("--color-line-strong");
    const accent = tok("--color-accent-strong");
    const ok = tok("--color-ok");

    mermaid.initialize({
      startOnLoad: false,
      securityLevel: "strict",
      theme: "base",
      themeVariables: {
        fontFamily: 'ui-monospace, "SF Mono", Menlo, Monaco, Consolas, monospace',
        fontSize: "13px",
        background: "transparent",
        primaryColor: "transparent",
        primaryTextColor: ink,
        primaryBorderColor: line,
        secondaryColor: "transparent",
        tertiaryColor: "transparent",
        lineColor: ink_soft,
        textColor: ink,
        actorBkg: "transparent",
        actorBorder: line,
        actorTextColor: ink,
        actorLineColor: faint,
        signalColor: ink_soft,
        signalTextColor: ink,
        labelBoxBkgColor: "transparent",
        labelBoxBorderColor: line,
        labelTextColor: ink_soft,
        loopTextColor: muted,
        noteBkgColor: "transparent",
        noteBorderColor: line,
        noteTextColor: muted,
        activationBkgColor: "transparent",
        activationBorderColor: line,
        sequenceNumberColor: ink,
        nodeBorder: line,
        clusterBkg: "transparent",
        clusterBorder: line,
        edgeLabelBackground: "transparent",
        mainBkg: "transparent",
        altBackground: "transparent",
        nodeTextColor: ink,
        cScale0: accent,
        cScale1: ok,
      },
    });
    initializedTheme = theme;
  }
  return mermaid;
}

export function Mermaid({ code }: { code: string }) {
  const reactId = useId();
  const idRef = useRef(`m${reactId.replace(/:/g, "-")}`);
  const [svg, setSvg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    void (async () => {
      try {
        const mermaid = await getMermaid();
        const { svg: out } = await mermaid.render(idRef.current, code);
        if (!cancelled) setSvg(out);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [code]);

  useEffect(() => {
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const handler = () => {
      initializedTheme = null;
      setSvg((prev) => prev);
    };
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  if (error) {
    return (
      <div className="mermaid-error">
        <div className="mermaid-error-head">Couldn't render diagram</div>
        <pre className="mermaid-error-body">{code}</pre>
      </div>
    );
  }

  if (!svg) {
    return <div className="mermaid-loading">Rendering…</div>;
  }

  return (
    <>
      <div className="mermaid-block group/mermaid">
        <button
          type="button"
          onClick={() => setExpanded(true)}
          aria-label="Expand diagram"
          title="Expand"
          className="mermaid-expand"
        >
          <Maximize2 size={12} strokeWidth={1.8} />
        </button>
        <div className="mermaid-svg" dangerouslySetInnerHTML={{ __html: svg }} />
      </div>
      {expanded && <MermaidViewer svg={svg} onClose={() => setExpanded(false)} />}
    </>
  );
}

const MIN_ZOOM = 0.4;
const MAX_ZOOM = 4;
const STEP = 0.2;

function MermaidViewer({ svg, onClose }: { svg: string; onClose: () => void }) {
  const [zoom, setZoom] = useState(1);
  const root = document.querySelector("#app");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "+" || e.key === "=") setZoom((z) => Math.min(MAX_ZOOM, +(z + STEP).toFixed(2)));
      else if (e.key === "-" || e.key === "_") setZoom((z) => Math.max(MIN_ZOOM, +(z - STEP).toFixed(2)));
      else if (e.key === "0") setZoom(1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!root) return null;

  return createPortal(
    <div
      className="absolute inset-0 z-50 grid grid-rows-[auto_minmax(0,1fr)] p-8 bg-[rgba(0,0,0,0.32)] backdrop-blur-md animate-fade-in"
      onClick={onClose}
    >
      <div
        className="self-center justify-self-center w-[min(1280px,calc(100vw-80px))] max-h-[calc(100vh-80px)] grid grid-rows-[auto_minmax(0,1fr)] rounded-2xl bg-surface shadow-[var(--shadow-pop)] animate-pop-in overflow-hidden"
        onClick={(e) => e.stopPropagation()}
        style={{ gridRow: "1 / span 2" }}
      >
        <header className="flex items-center justify-between gap-2 px-4 pt-3 pb-2 border-b border-line-soft">
          <div className="text-[11px] font-medium uppercase tracking-[0.08em] text-faint">
            Diagram
          </div>
          <div className="flex items-center gap-1">
            <ToolbarButton
              label="Zoom out"
              onClick={() => setZoom((z) => Math.max(MIN_ZOOM, +(z - STEP).toFixed(2)))}
              disabled={zoom <= MIN_ZOOM}
            >
              <Minus size={13} strokeWidth={1.8} />
            </ToolbarButton>
            <span className="w-12 text-center text-[11.5px] tabular-nums text-muted select-none">
              {Math.round(zoom * 100)}%
            </span>
            <ToolbarButton
              label="Zoom in"
              onClick={() => setZoom((z) => Math.min(MAX_ZOOM, +(z + STEP).toFixed(2)))}
              disabled={zoom >= MAX_ZOOM}
            >
              <Plus size={13} strokeWidth={1.8} />
            </ToolbarButton>
            <ToolbarButton label="Reset zoom" onClick={() => setZoom(1)}>
              <RotateCcw size={12} strokeWidth={1.8} />
            </ToolbarButton>
            <span className="w-px h-4 bg-line mx-1" />
            <ToolbarButton label="Close" onClick={onClose}>
              <X size={13} strokeWidth={1.8} />
            </ToolbarButton>
          </div>
        </header>
        <div className="overflow-auto scroll-thin bg-code-bg">
          <div
            className="mermaid-viewer-stage"
            style={{
              transform: `scale(${zoom})`,
              transformOrigin: "top left",
              padding: "32px",
              display: "inline-block",
              minWidth: "100%",
            }}
            dangerouslySetInnerHTML={{ __html: svg }}
          />
        </div>
      </div>
    </div>,
    root,
  );
}

function ToolbarButton({
  label,
  onClick,
  disabled,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      className="grid place-items-center w-7 h-7 rounded-md text-muted hover:bg-surface-soft hover:text-ink disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
    >
      {children}
    </button>
  );
}
