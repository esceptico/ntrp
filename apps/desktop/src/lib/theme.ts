import { useEffect } from "react";
import {
  useStore,
  type GlassBlur,
  type GlassDensity,
  type GlassRim,
  type GlassTexture,
  type PaletteId,
  type ThemeChoice,
} from "../store";
import { PALETTES } from "./palettes";

const DARK_QUERY = "(prefers-color-scheme: dark)";
const PALETTE_CLASSES = PALETTES.map((p) => `palette-${p.id}`);
const GLASS_CLASSES: Record<GlassDensity, string> = {
  airy: "glass-density-airy",
  balanced: "glass-density-balanced",
  solid: "glass-density-solid",
};
const GLASS_BLUR_CLASSES: Record<GlassBlur, string> = {
  crisp: "glass-blur-crisp",
  balanced: "glass-blur-balanced",
  soft: "glass-blur-soft",
};
const GLASS_RIM_CLASSES: Record<GlassRim, string> = {
  quiet: "glass-rim-quiet",
  balanced: "glass-rim-balanced",
  sharp: "glass-rim-sharp",
};
const GLASS_TEXTURE_CLASSES: Record<GlassTexture, string> = {
  clean: "glass-texture-clean",
  auto: "glass-texture-auto",
  grain: "glass-texture-grain",
};

function resolveDark(choice: ThemeChoice): boolean {
  if (choice === "dark") return true;
  if (choice === "light") return false;
  return window.matchMedia(DARK_QUERY).matches;
}

function apply(
  choice: ThemeChoice,
  palette: PaletteId,
  glassDensity: GlassDensity,
  glassBlur: GlassBlur,
  glassRim: GlassRim,
  glassTexture: GlassTexture,
): void {
  const root = document.documentElement;
  if (resolveDark(choice)) root.classList.add("dark");
  else root.classList.remove("dark");
  // Drop any other palette- class first so we don't accumulate stale ones.
  for (const cls of PALETTE_CLASSES) root.classList.remove(cls);
  root.classList.add(`palette-${palette}`);
  for (const cls of [
    ...Object.values(GLASS_CLASSES),
    ...Object.values(GLASS_BLUR_CLASSES),
    ...Object.values(GLASS_RIM_CLASSES),
    ...Object.values(GLASS_TEXTURE_CLASSES),
  ]) root.classList.remove(cls);
  root.classList.add(GLASS_CLASSES[glassDensity]);
  root.classList.add(GLASS_BLUR_CLASSES[glassBlur]);
  root.classList.add(GLASS_RIM_CLASSES[glassRim]);
  root.classList.add(GLASS_TEXTURE_CLASSES[glassTexture]);
}

/** Effect that keeps the <html> `dark` + `palette-<id>` classes in sync
 *  with the user's prefs. When theme is "system", also subscribes to
 *  OS-level changes so the app flips automatically without a reload. */
export function useThemeEffect(): void {
  const theme = useStore((s) => s.prefs.theme);
  const palette = useStore((s) => s.prefs.palette);
  const glassDensity = useStore((s) => s.prefs.glassDensity);
  const glassBlur = useStore((s) => s.prefs.glassBlur);
  const glassRim = useStore((s) => s.prefs.glassRim);
  const glassTexture = useStore((s) => s.prefs.glassTexture);

  useEffect(() => {
    apply(theme, palette, glassDensity, glassBlur, glassRim, glassTexture);
    if (theme !== "system") return;
    const mql = window.matchMedia(DARK_QUERY);
    const onChange = () =>
      apply("system", palette, glassDensity, glassBlur, glassRim, glassTexture);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [theme, palette, glassDensity, glassBlur, glassRim, glassTexture]);
}
