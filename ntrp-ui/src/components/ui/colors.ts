/**
 * NTRP Color System — dark/light bases + curated themes + configurable accent.
 *
 * Base themes (dark, light) support user-selected accent overlay.
 * Curated themes (tokyonight, catppuccin, rosepine, nord) have built-in accents.
 */

import { useSyncExternalStore } from "react";

export type AccentColor = "blue" | "cyan" | "green" | "purple" | "rose" | "amber" | "red";
export const accentNames: AccentColor[] = ["blue", "cyan", "green", "purple", "rose", "amber", "red"];

type Palette = {
  text: { primary: string; secondary: string; muted: string; disabled: string };
  status: { success: string; error: string; warning: string; processing: string; processingShimmer: string };
  selection: { active: string; indicator: string };
  panel: { title: string; subtitle: string };
  tabs: { active: string; inactive: string; separator: string };
  list: { itemText: string; itemTextSelected: string; itemDetail: string; scrollArrow: string };
  keyValue: { label: string; value: string };
  background: { base: string | undefined; panel: string | undefined; element: string | undefined; menu: string };
  border: string;
  divider: string;
  footer: string;
  diff: { added: string; addedBg: string; removed: string; removedBg: string };
  tool: { pending: string; running: string; completed: string; error: string };
  contrast: string;
  accent: { primary: string; shimmer: string };
};

// -- Base palettes (pure monochrome) ----------------------------------------

const bases = {

  dark: {
    text: { primary: "#c8c8c8", secondary: "#888888", muted: "#7a7a7a", disabled: "#505050" },
    status: { success: "#888888", error: "#888888", warning: "#888888", processing: "#c8c8c8", processingShimmer: "#e0e0e0" },
    selection: { active: "#c8c8c8", indicator: "#c8c8c8" },
    panel: { title: "#c8c8c8", subtitle: "#888888" },
    tabs: { active: "#c8c8c8", inactive: "#7a7a7a", separator: "#3a3a3a" },
    list: { itemText: "#c8c8c8", itemTextSelected: "#c8c8c8", itemDetail: "#7a7a7a", scrollArrow: "#7a7a7a" },
    keyValue: { label: "#c8c8c8", value: "#888888" },
    background: { base: "#181818", panel: "#101010", element: "#2c2c2c", menu: "#2c2c2c" },
    border: "#3a3a3a",
    divider: "#3a3a3a",
    footer: "#7a7a7a",
    diff: { added: "#888888", addedBg: "#2c2c2c", removed: "#6a6a6a", removedBg: "#212121" },
    tool: { pending: "#7a7a7a", running: "#888888", completed: "#c8c8c8", error: "#888888" },
    contrast: "#000000",
    accent: { primary: "#c8c8c8", shimmer: "#e0e0e0" },
  },

  light: {
    text: { primary: "#1a1717", secondary: "#4a4747", muted: "#6b6868", disabled: "#a8a5a5" },
    status: { success: "#4a4747", error: "#4a4747", warning: "#4a4747", processing: "#1a1717", processingShimmer: "#4a4747" },
    selection: { active: "#1a1717", indicator: "#1a1717" },
    panel: { title: "#1a1717", subtitle: "#4a4747" },
    tabs: { active: "#1a1717", inactive: "#6b6868", separator: "#c5c1c1" },
    list: { itemText: "#1a1717", itemTextSelected: "#1a1717", itemDetail: "#6b6868", scrollArrow: "#6b6868" },
    keyValue: { label: "#1a1717", value: "#4a4747" },
    background: { base: "#eeebeb", panel: "#f5f2f2", element: "#e2dfdf", menu: "#e2dfdf" },
    border: "#c5c1c1",
    divider: "#c5c1c1",
    footer: "#6b6868",
    diff: { added: "#4a4747", addedBg: "#e2dfdf", removed: "#6b6868", removedBg: "#d5d1d1" },
    tool: { pending: "#6b6868", running: "#4a4747", completed: "#1a1717", error: "#4a4747" },
    contrast: "#eeebeb",
    accent: { primary: "#1a1717", shimmer: "#4a4747" },
  },

} satisfies Record<string, Palette>;

// -- Accent definitions (dark/light variants) -------------------------------

const accents = {
  blue:   { dark: { primary: "#7aa2f7", shimmer: "#82aaff" }, light: { primary: "#3b6dd4", shimmer: "#5a88e0" } },
  cyan:   { dark: { primary: "#88c0d0", shimmer: "#8fbcbb" }, light: { primary: "#2a8a9a", shimmer: "#3d9eab" } },
  green:  { dark: { primary: "#8ec07c", shimmer: "#a7c080" }, light: { primary: "#4a8a3e", shimmer: "#5c9e4e" } },
  purple: { dark: { primary: "#b4befe", shimmer: "#c4a7e7" }, light: { primary: "#7b5ebd", shimmer: "#9070d0" } },
  rose:   { dark: { primary: "#ebbcba", shimmer: "#f5c2e7" }, light: { primary: "#c06070", shimmer: "#d07585" } },
  amber:  { dark: { primary: "#e6b450", shimmer: "#ffb454" }, light: { primary: "#b08520", shimmer: "#c49830" } },
  red:    { dark: { primary: "#e06c75", shimmer: "#f07080" }, light: { primary: "#c04048", shimmer: "#d05058" } },
} as const;

export { accents };

// -- Curated themes ---------------------------------------------------------

const curatedThemes = {

  flexoki: {
    text: { primary: "#CECDC3", secondary: "#9C9B95", muted: "#878580", disabled: "#575653" },
    status: { success: "#879A39", error: "#D14D41", warning: "#DA702C", processing: "#DA702C", processingShimmer: "#D0A215" },
    selection: { active: "#DA702C", indicator: "#DA702C" },
    panel: { title: "#CECDC3", subtitle: "#9C9B95" },
    tabs: { active: "#DA702C", inactive: "#878580", separator: "#343331" },
    list: { itemText: "#CECDC3", itemTextSelected: "#CECDC3", itemDetail: "#878580", scrollArrow: "#878580" },
    keyValue: { label: "#CECDC3", value: "#9C9B95" },
    background: { base: "#100F0F", panel: "#1C1B1A", element: "#282726", menu: "#282726" },
    border: "#575653",
    divider: "#575653",
    footer: "#878580",
    diff: { added: "#879A39", addedBg: "#1A2D1A", removed: "#D14D41", removedBg: "#2D1A1A" },
    tool: { pending: "#878580", running: "#DA702C", completed: "#879A39", error: "#D14D41" },
    contrast: "#000000",
    accent: { primary: "#DA702C", shimmer: "#D0A215" },
  },

  onedark: {
    text: { primary: "#ABB2BF", secondary: "#848B98", muted: "#636D83", disabled: "#495163" },
    status: { success: "#98C379", error: "#E06C75", warning: "#D19A66", processing: "#61AFEF", processingShimmer: "#C678DD" },
    selection: { active: "#61AFEF", indicator: "#61AFEF" },
    panel: { title: "#ABB2BF", subtitle: "#848B98" },
    tabs: { active: "#61AFEF", inactive: "#636D83", separator: "#2C313A" },
    list: { itemText: "#ABB2BF", itemTextSelected: "#ABB2BF", itemDetail: "#636D83", scrollArrow: "#636D83" },
    keyValue: { label: "#ABB2BF", value: "#848B98" },
    background: { base: "#282C34", panel: "#21252B", element: "#353B45", menu: "#353B45" },
    border: "#393F4A",
    divider: "#393F4A",
    footer: "#636D83",
    diff: { added: "#98C379", addedBg: "#2C382B", removed: "#E06C75", removedBg: "#3A2D2F" },
    tool: { pending: "#636D83", running: "#61AFEF", completed: "#98C379", error: "#E06C75" },
    contrast: "#000000",
    accent: { primary: "#61AFEF", shimmer: "#C678DD" },
  },

  vercel: {
    text: { primary: "#EDEDED", secondary: "#A1A1A1", muted: "#878787", disabled: "#454545" },
    status: { success: "#46A758", error: "#E5484D", warning: "#FFB224", processing: "#0070F3", processingShimmer: "#52A8FF" },
    selection: { active: "#0070F3", indicator: "#0070F3" },
    panel: { title: "#EDEDED", subtitle: "#A1A1A1" },
    tabs: { active: "#52A8FF", inactive: "#878787", separator: "#1F1F1F" },
    list: { itemText: "#EDEDED", itemTextSelected: "#EDEDED", itemDetail: "#878787", scrollArrow: "#878787" },
    keyValue: { label: "#EDEDED", value: "#A1A1A1" },
    background: { base: "#000000", panel: "#0A0A0A", element: "#1A1A1A", menu: "#1A1A1A" },
    border: "#292929",
    divider: "#292929",
    footer: "#878787",
    diff: { added: "#63C46D", addedBg: "#0B1D0F", removed: "#FF6166", removedBg: "#2A1314" },
    tool: { pending: "#878787", running: "#0070F3", completed: "#46A758", error: "#E5484D" },
    contrast: "#000000",
    accent: { primary: "#0070F3", shimmer: "#52A8FF" },
  },

  nord: {
    text: { primary: "#ECEFF4", secondary: "#D8DEE9", muted: "#97A1B2", disabled: "#4C566A" },
    status: { success: "#A3BE8C", error: "#BF616A", warning: "#D08770", processing: "#88C0D0", processingShimmer: "#81A1C1" },
    selection: { active: "#88C0D0", indicator: "#88C0D0" },
    panel: { title: "#ECEFF4", subtitle: "#D8DEE9" },
    tabs: { active: "#88C0D0", inactive: "#97A1B2", separator: "#434C5E" },
    list: { itemText: "#ECEFF4", itemTextSelected: "#ECEFF4", itemDetail: "#97A1B2", scrollArrow: "#97A1B2" },
    keyValue: { label: "#ECEFF4", value: "#D8DEE9" },
    background: { base: "#2E3440", panel: "#3B4252", element: "#434C5E", menu: "#434C5E" },
    border: "#4C566A",
    divider: "#4C566A",
    footer: "#97A1B2",
    diff: { added: "#A3BE8C", addedBg: "#303D38", removed: "#BF616A", removedBg: "#3D3038" },
    tool: { pending: "#97A1B2", running: "#88C0D0", completed: "#A3BE8C", error: "#BF616A" },
    contrast: "#000000",
    accent: { primary: "#88C0D0", shimmer: "#81A1C1" },
  },

} satisfies Record<string, Palette>;

// -- Build palettes map -----------------------------------------------------

const palettes: Record<string, Palette> = { ...bases, ...curatedThemes };

export { palettes };
export type Theme = string;
export const themeNames = Object.keys(palettes);

export function isBaseTheme(theme: string): boolean {
  return theme === "dark" || theme === "light";
}

// -- Runtime state (mutated in place by setTheme) ---------------------------

export const currentAccent = { primary: "#7aa2f7", shimmer: "#82aaff" };

export const colors: Omit<Palette, "accent"> = {
  text: { ...palettes.dark.text },
  status: { ...palettes.dark.status },
  selection: { ...palettes.dark.selection },
  panel: { ...palettes.dark.panel },
  tabs: { ...palettes.dark.tabs },
  list: { ...palettes.dark.list },
  keyValue: { ...palettes.dark.keyValue },
  background: { ...palettes.dark.background },
  border: palettes.dark.border,
  divider: palettes.dark.divider,
  footer: palettes.dark.footer,
  diff: { ...palettes.dark.diff },
  tool: { ...palettes.dark.tool },
  contrast: palettes.dark.contrast,
};

// Theme version — incremented on every setTheme call.
let _themeVersion = 0;
const _listeners = new Set<() => void>();

export function getThemeVersion() { return _themeVersion; }
export function subscribeThemeVersion(cb: () => void) {
  _listeners.add(cb);
  return () => { _listeners.delete(cb); };
}

export function setTheme(theme: Theme, accent?: AccentColor, transparentBg?: boolean) {
  const p = palettes[theme];
  if (!p) return;

  Object.assign(colors.text, p.text);
  Object.assign(colors.status, p.status);
  Object.assign(colors.selection, p.selection);
  Object.assign(colors.panel, p.panel);
  Object.assign(colors.tabs, p.tabs);
  Object.assign(colors.list, p.list);
  Object.assign(colors.keyValue, p.keyValue);
  Object.assign(colors.background, p.background);
  if (transparentBg) {
    colors.background.base = undefined;
    colors.background.panel = undefined;
    colors.background.element = undefined;
  }
  colors.border = p.border;
  colors.divider = p.divider;
  colors.footer = p.footer;
  Object.assign(colors.diff, p.diff);
  Object.assign(colors.tool, p.tool);
  colors.contrast = p.contrast;

  if (isBaseTheme(theme) && accent && accents[accent]) {
    const a = accents[accent][theme as "dark" | "light"];
    Object.assign(colors.selection, { active: a.primary, indicator: a.primary });
    currentAccent.primary = a.primary;
    currentAccent.shimmer = a.shimmer;
  } else {
    currentAccent.primary = p.accent.primary;
    currentAccent.shimmer = p.accent.shimmer;
  }

  _themeVersion++;
  for (const cb of _listeners) cb();
}

export function useThemeVersion() {
  return useSyncExternalStore(subscribeThemeVersion, getThemeVersion);
}
