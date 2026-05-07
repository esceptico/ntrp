export type PaletteId =
  | "warm"
  | "graphite"
  | "vercel"
  | "raycast"
  | "github"
  | "linear"
  | "notion"
  | "catppuccin";

export interface PaletteSwatch {
  /** Background color of the Aa chip. */
  bg: string;
  /** Accent / "Aa" text color. */
  accent: string;
}

export interface PaletteMeta {
  id: PaletteId;
  label: string;
  light: PaletteSwatch;
  dark: PaletteSwatch;
}

// Brand palettes use officially-documented colors where available
// (Vercel Geist, GitHub Primer Primitives, Linear brand, Catppuccin
// spec). Notion / Raycast publish only their wordmark color so the
// surface neutrals there are best-effort approximations from product
// chrome.
export const PALETTES: PaletteMeta[] = [
  {
    id: "warm",
    label: "Warm",
    light: { bg: "#ffffff", accent: "#b85c1f" },
    dark: { bg: "#1c1b1a", accent: "#da702c" },
  },
  {
    id: "graphite",
    label: "Graphite",
    light: { bg: "#ffffff", accent: "#0f8d76" },
    dark: { bg: "#101112", accent: "#55d6be" },
  },
  {
    id: "vercel",
    label: "Vercel",
    light: { bg: "#ffffff", accent: "#0068d6" },
    dark: { bg: "#0a0a0a", accent: "#52a8ff" },
  },
  {
    id: "raycast",
    label: "Raycast",
    light: { bg: "#ffffff", accent: "#ff6363" },
    dark: { bg: "#1a1a1a", accent: "#ff6363" },
  },
  {
    id: "github",
    label: "GitHub",
    light: { bg: "#ffffff", accent: "#0969da" },
    dark: { bg: "#0d1117", accent: "#58a6ff" },
  },
  {
    id: "linear",
    label: "Linear",
    light: { bg: "#ffffff", accent: "#5e6ad2" },
    dark: { bg: "#1c1c1f", accent: "#7170ff" },
  },
  {
    id: "notion",
    label: "Notion",
    light: { bg: "#ffffff", accent: "#0f0f0f" },
    dark: { bg: "#191919", accent: "#ffffff" },
  },
  {
    id: "catppuccin",
    label: "Catppuccin",
    light: { bg: "#eff1f5", accent: "#1e66f5" },
    dark: { bg: "#1e1e2e", accent: "#89b4fa" },
  },
];

export const PALETTE_BY_ID: Record<PaletteId, PaletteMeta> = Object.fromEntries(
  PALETTES.map((p) => [p.id, p]),
) as Record<PaletteId, PaletteMeta>;
