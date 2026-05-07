import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "motion/react";
import { Check, Copy, Maximize2, Minimize2, Minus, Plus, RotateCcw } from "lucide-react";
import clsx from "clsx";
import { getMermaid, invalidateMermaidTheme } from "../lib/mermaidTheme";

const MODAL_EASE = [0.2, 0.8, 0.2, 1] as const;

const RENDER_DEBOUNCE_MS = 400;
const MIN_ZOOM = 0.1;
const MAX_ZOOM = 5;
const ZOOM_STEP = 1.2;

interface ViewState {
  zoom: number;
  x: number;
  y: number;
}

export function Mermaid({ code }: { code: string }) {
  const reactId = useId();
  const idRef = useRef(`m${reactId.replace(/:/g, "-")}`);
  const [svg, setSvg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stableCode, setStableCode] = useState(code);

  useEffect(() => {
    if (code === stableCode) return;
    const handle = setTimeout(() => setStableCode(code), RENDER_DEBOUNCE_MS);
    return () => clearTimeout(handle);
  }, [code, stableCode]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const mermaid = await getMermaid();
        const { svg: out } = await mermaid.render(idRef.current, stableCode);
        if (!cancelled) {
          setSvg(out);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [stableCode]);

  useEffect(() => {
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const handler = () => {
      invalidateMermaidTheme();
      setSvg((prev) => prev);
    };
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  if (!svg && error) {
    return <MermaidErrorBlock source={code} message={error} />;
  }
  if (!svg) {
    return <div className="mermaid-loading">Rendering…</div>;
  }
  return <MermaidPanel svg={svg} source={code} />;
}

/** Top-level panel: holds fullscreen state and either renders the inline
 *  panel or a fullscreen portal containing the same panel. Each variant
 *  remounts `PanelInner`, which re-runs fit-to-view for the new size. */
function MermaidPanel({ svg, source }: { svg: string; source: string }) {
  const [fullscreen, setFullscreen] = useState(false);
  const toggle = () => setFullscreen((v) => !v);
  const root = document.querySelector("#app");

  // Inline panel is always mounted; the fullscreen overlay renders into a
  // portal under AnimatePresence so closing fades + scales back down. The
  // inline panel sits behind the opaque modal during the toggle, so the
  // exit animation has something to land on without a flash.
  return (
    <>
      <PanelInner svg={svg} source={source} fullscreen={false} onToggleFullscreen={toggle} />
      {root &&
        createPortal(
          <AnimatePresence>
            {fullscreen && (
              <motion.div
                key="mermaid-fullscreen"
                className="absolute inset-0 z-50 bg-[rgba(0,0,0,0.4)] backdrop-blur-md p-6"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2, ease: MODAL_EASE }}
                onClick={() => setFullscreen(false)}
              >
                <motion.div
                  className="w-full h-full"
                  initial={{ opacity: 0, scale: 0.96, y: 6 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.96, y: 6 }}
                  transition={{ duration: 0.22, ease: MODAL_EASE }}
                  onClick={(e) => e.stopPropagation()}
                >
                  <PanelInner svg={svg} source={source} fullscreen onToggleFullscreen={toggle} />
                </motion.div>
              </motion.div>
            )}
          </AnimatePresence>,
          root,
        )}
    </>
  );
}

function PanelInner({
  svg,
  source,
  fullscreen,
  onToggleFullscreen,
}: {
  svg: string;
  source: string;
  fullscreen: boolean;
  onToggleFullscreen: () => void;
}) {
  const surfaceRef = useRef<HTMLDivElement>(null);
  const innerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGElement | null>(null);
  const naturalRef = useRef<{ w: number; h: number } | null>(null);
  const [view, setView] = useState<ViewState>({ zoom: 1, x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const [copied, setCopied] = useState(false);
  const dragRef = useRef<{ startX: number; startY: number; viewX: number; viewY: number } | null>(null);

  const onCopy = async () => {
    await window.ntrpDesktop?.clipboard?.writeText(source);
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  };

  // Inject the SVG once, capture natural size, fit-to-view.
  useEffect(() => {
    const inner = innerRef.current;
    const surface = surfaceRef.current;
    if (!inner || !surface) return;
    inner.innerHTML = svg;
    const el = inner.querySelector("svg") as SVGElement | null;
    svgRef.current = el;
    if (!el) return;
    el.style.transformOrigin = "0 0";
    el.style.willChange = "transform";
    el.style.transition = "none"; // snappy

    const sBox = el.getBoundingClientRect();
    naturalRef.current = { w: sBox.width || 1, h: sBox.height || 1 };

    const fit = computeFit(surface, naturalRef.current);
    setView(fit);
  }, [svg]);

  // Apply the transform on every view change.
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    el.style.transform = `translate3d(${view.x}px, ${view.y}px, 0) scale(${view.zoom})`;
  }, [view]);

  // Wheel zoom (cursor-anchored). In inline mode require Cmd/Ctrl so the
  // chat keeps scrolling normally; in fullscreen plain wheel zooms.
  useEffect(() => {
    const surface = surfaceRef.current;
    if (!surface) return;
    const handler = (e: WheelEvent) => {
      const modifier = e.ctrlKey || e.metaKey;
      if (!fullscreen && !modifier) return;
      e.preventDefault();
      const rect = surface.getBoundingClientRect();
      const cx = e.clientX - rect.left;
      const cy = e.clientY - rect.top;
      const delta = e.deltaY > 0 ? 0.9 : 1.1;
      setView((prev) => zoomTowards(prev, prev.zoom * delta, cx, cy));
    };
    surface.addEventListener("wheel", handler, { passive: false });
    return () => surface.removeEventListener("wheel", handler);
  }, [fullscreen]);

  const onMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    setDragging(true);
    dragRef.current = { startX: e.clientX, startY: e.clientY, viewX: view.x, viewY: view.y };
  };
  const onMouseMove = (e: React.MouseEvent) => {
    const drag = dragRef.current;
    if (!drag) return;
    setView((prev) => ({
      ...prev,
      x: drag.viewX + (e.clientX - drag.startX),
      y: drag.viewY + (e.clientY - drag.startY),
    }));
  };
  const endDrag = () => {
    setDragging(false);
    dragRef.current = null;
  };

  // Toolbar zoom anchors on the surface center so the diagram stays in
  // view rather than drifting toward the corner.
  const zoomBy = (factor: number) => {
    const surface = surfaceRef.current;
    if (!surface) return;
    const rect = surface.getBoundingClientRect();
    setView((prev) => zoomTowards(prev, prev.zoom * factor, rect.width / 2, rect.height / 2));
  };

  const fitToView = () => {
    const surface = surfaceRef.current;
    const natural = naturalRef.current;
    if (!surface || !natural) return;
    setView(computeFit(surface, natural));
  };

  // Esc exits fullscreen. Re-fit when toggling so the diagram lands sized
  // to whichever surface it's currently in.
  useEffect(() => {
    if (!fullscreen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onToggleFullscreen();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [fullscreen, onToggleFullscreen]);

  return (
    <div className={clsx("mermaid-panel", fullscreen && "fullscreen")}>
      <header className="mermaid-panel-header">
        <div className="mermaid-panel-title">Diagram</div>
        <div className="mermaid-panel-toolbar">
          <ToolbarButton
            label="Zoom out"
            onClick={() => zoomBy(1 / ZOOM_STEP)}
            disabled={view.zoom <= MIN_ZOOM + 1e-3}
          >
            <Minus size={13} strokeWidth={1.8} />
          </ToolbarButton>
          <span className="mermaid-panel-zoom">{Math.round(view.zoom * 100)}%</span>
          <ToolbarButton
            label="Zoom in"
            onClick={() => zoomBy(ZOOM_STEP)}
            disabled={view.zoom >= MAX_ZOOM - 1e-3}
          >
            <Plus size={13} strokeWidth={1.8} />
          </ToolbarButton>
          <ToolbarButton label="Fit to view" onClick={fitToView}>
            <RotateCcw size={12} strokeWidth={1.8} />
          </ToolbarButton>
          <span className="mermaid-panel-divider" />
          <ToolbarButton
            label={copied ? "Copied" : "Copy source"}
            onClick={() => void onCopy()}
          >
            {copied ? (
              <Check size={13} strokeWidth={2.4} className="text-ok" />
            ) : (
              <Copy size={13} strokeWidth={1.8} />
            )}
          </ToolbarButton>
          <ToolbarButton
            label={fullscreen ? "Exit fullscreen" : "Fullscreen"}
            onClick={onToggleFullscreen}
          >
            {fullscreen ? (
              <Minimize2 size={13} strokeWidth={1.8} />
            ) : (
              <Maximize2 size={13} strokeWidth={1.8} />
            )}
          </ToolbarButton>
        </div>
      </header>
      <div
        ref={surfaceRef}
        className={clsx("mermaid-panel-surface", dragging && "is-dragging")}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={endDrag}
        onMouseLeave={endDrag}
      >
        <div ref={innerRef} className="mermaid-panel-inner" />
      </div>
    </div>
  );
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function zoomTowards(prev: ViewState, requestedZoom: number, anchorX: number, anchorY: number): ViewState {
  const next = clamp(requestedZoom, MIN_ZOOM, MAX_ZOOM);
  if (next === prev.zoom) return prev;
  const ratio = next / prev.zoom;
  return {
    zoom: next,
    x: anchorX + (prev.x - anchorX) * ratio,
    y: anchorY + (prev.y - anchorY) * ratio,
  };
}

function computeFit(surface: HTMLElement, natural: { w: number; h: number }): ViewState {
  const rect = surface.getBoundingClientRect();
  // Margin so the diagram isn't flush against the surface edges.
  const pad = 16;
  const fit = Math.min(
    (rect.width - pad * 2) / natural.w,
    (rect.height - pad * 2) / natural.h,
    1,
  );
  return {
    zoom: fit,
    x: (rect.width - natural.w * fit) / 2,
    y: (rect.height - natural.h * fit) / 2,
  };
}

function MermaidErrorBlock({ source, message }: { source: string; message: string }) {
  const [copied, setCopied] = useState(false);
  const onCopy = async () => {
    await window.ntrpDesktop?.clipboard?.writeText(source);
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  };
  return (
    <div className="mermaid-error">
      <div className="mermaid-error-row">
        <strong className="mermaid-error-head">Couldn't render diagram</strong>
        <button
          type="button"
          onClick={() => void onCopy()}
          aria-label={copied ? "Copied" : "Copy source"}
          title={copied ? "Copied" : "Copy source"}
          className="mermaid-error-copy"
        >
          {copied ? <Check size={12} strokeWidth={2.4} /> : <Copy size={12} strokeWidth={1.8} />}
        </button>
      </div>
      <pre className="mermaid-error-body">{source}</pre>
      {message && <div className="mermaid-error-detail">{message}</div>}
    </div>
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
