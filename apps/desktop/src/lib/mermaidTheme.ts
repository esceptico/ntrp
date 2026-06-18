// Mermaid initialization: lazy-load the library on first use, pull palette
// values from our CSS tokens so light/dark theme flips are picked up, and
// disable per-diagram-type responsive sizing so the rendered <svg> carries
// absolute pixel dimensions (the panel relies on a real natural size for
// fit-to-view math).

// Mermaid's internal color lib (khroma) can't reliably parse all CSS color
// formats, so normalize every token to sRGB rgb()/rgba() via a canvas probe.
let probeCtx: CanvasRenderingContext2D | null = null;

function toRgb(color: string): string {
  if (!color || color === "transparent") return color;
  if (!probeCtx) {
    probeCtx = document
      .createElement("canvas")
      .getContext("2d", { willReadFrequently: true });
  }
  if (!probeCtx) return color;
  probeCtx.clearRect(0, 0, 1, 1);
  probeCtx.fillStyle = color; // invalid values are ignored → transparent black
  probeCtx.fillRect(0, 0, 1, 1);
  const [r, g, b, a] = probeCtx.getImageData(0, 0, 1, 1).data;
  return a === 255 ? `rgb(${r}, ${g}, ${b})` : `rgba(${r}, ${g}, ${b}, ${a / 255})`;
}

/** Read a CSS custom property from :root, normalized to an rgb/hex string. */
function tok(name: string): string {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return toRgb(raw);
}

function currentTheme(): "light" | "dark" {
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

let initPromise: Promise<typeof import("mermaid").default> | null = null;
let initializedTheme: "light" | "dark" | null = null;

/** Lazy-load mermaid on first use; re-initialize when the OS theme flips
 *  so freshly-rendered diagrams pick up the new palette. */
export async function getMermaid(): Promise<typeof import("mermaid").default> {
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
    const surfaceSunken = tok("--color-surface-sunken");
    const onInk = tok("--color-on-ink");

    mermaid.initialize({
      startOnLoad: false,
      securityLevel: "strict",
      theme: "neutral",
      // useMaxWidth: false makes mermaid emit absolute pixel sizes on the
      // <svg> instead of `style="width:100%"`. The panel needs a real
      // natural size for fit-to-view math.
      flowchart: { useMaxWidth: false },
      sequence: { useMaxWidth: false },
      class: { useMaxWidth: false },
      state: { useMaxWidth: false },
      er: { useMaxWidth: false },
      gantt: { useMaxWidth: false },
      journey: { useMaxWidth: false },
      timeline: { useMaxWidth: false },
      mindmap: { useMaxWidth: false },
      pie: { useMaxWidth: false },
      quadrantChart: { useMaxWidth: false },
      xyChart: { useMaxWidth: false },
      requirement: { useMaxWidth: false },
      gitGraph: { useMaxWidth: false },
      themeVariables: {
        fontSize: "13px",
        background: "transparent",
        textColor: ink,
        lineColor: ink_soft,
        actorBkg: "transparent",
        actorBorder: line,
        actorTextColor: ink,
        actorLineColor: faint,
        signalColor: ink_soft,
        signalTextColor: ink,
        labelBoxBkgColor: "transparent",
        labelBoxBorderColor: line,
        labelTextColor: ink,
        loopTextColor: muted,
        noteBkgColor: "transparent",
        noteBorderColor: line,
        noteTextColor: ink,
        // Activation bar (the rect over a participant's lifeline while
        // busy). Transparent fill made it almost invisible against the
        // panel background; a tinted fill + muted border reads as a clear
        // but unobtrusive bar.
        activationBkgColor: surfaceSunken,
        activationBorderColor: muted,
        // mermaid fills the autonumber bubble with `actorTextColor` (dark);
        // the number text needs the contrasting on-ink color to be visible.
        sequenceNumberColor: onInk,
        altBackground: "transparent",
        cScale0: "transparent",
        cScale1: "transparent",
        cScale2: "transparent",
        cScaleLabel0: ink,
        cScaleLabel1: ink,
        cScaleLabel2: ink,
        primaryColor: "transparent",
        primaryTextColor: ink,
        primaryBorderColor: line,
        secondaryColor: "transparent",
        tertiaryColor: "transparent",
        nodeBorder: line,
        nodeTextColor: ink,
        clusterBkg: "transparent",
        clusterBorder: line,
        edgeLabelBackground: "transparent",
        mainBkg: "transparent",
      },
    });
    initializedTheme = theme;
  }
  return mermaid;
}

/** Force a re-initialization on the next `getMermaid()` call. Used when
 *  the OS theme changes so the next render picks up the new palette. */
export function invalidateMermaidTheme(): void {
  initializedTheme = null;
}
