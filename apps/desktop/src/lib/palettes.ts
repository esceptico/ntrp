export type PaletteId =
  | "warm"
  | "graphite"
  | "raycast"
  | "notion";

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

// Notion / Raycast publish only their wordmark color so the surface
// neutrals there are best-effort approximations from product chrome.
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
    id: "raycast",
    label: "Raycast",
    light: { bg: "#ffffff", accent: "#ff6363" },
    dark: { bg: "#1a1a1a", accent: "#ff6363" },
  },
  {
    id: "notion",
    label: "Notion",
    light: { bg: "#ffffff", accent: "#0f0f0f" },
    dark: { bg: "#191919", accent: "#ffffff" },
  },
];

export const PALETTE_BY_ID: Record<PaletteId, PaletteMeta> = Object.fromEntries(
  PALETTES.map((p) => [p.id, p]),
) as Record<PaletteId, PaletteMeta>;
