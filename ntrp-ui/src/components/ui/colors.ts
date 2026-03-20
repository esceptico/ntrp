/**
 * NTRP Color System — dark/light bases + curated themes + configurable accent.
 *
 * Base themes (dark, light) support user-selected accent overlay.
 * Curated themes have built-in accents and fixed palettes.
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

  cursor: {
    text: { primary: "#D6D6DD", secondary: "#A6A6A6", muted: "#7A797A", disabled: "#535353" },
    status: { success: "#15AC91", error: "#F14C4C", warning: "#EA7620", processing: "#228DF2", processingShimmer: "#359DFF" },
    selection: { active: "#228DF2", indicator: "#5B51EC" },
    panel: { title: "#D6D6DD", subtitle: "#A6A6A6" },
    tabs: { active: "#228DF2", inactive: "#7A797A", separator: "#383838" },
    list: { itemText: "#D6D6DD", itemTextSelected: "#D6D6DD", itemDetail: "#7A797A", scrollArrow: "#7A797A" },
    keyValue: { label: "#D6D6DD", value: "#A6A6A6" },
    background: { base: "#181818", panel: "#121212", element: "#212121", menu: "#292929" },
    border: "#383838",
    divider: "#383838",
    footer: "#7A797A",
    diff: { added: "#15AC91", addedBg: "#0B1D17", removed: "#F14C4C", removedBg: "#2A1314" },
    tool: { pending: "#7A797A", running: "#228DF2", completed: "#15AC91", error: "#F14C4C" },
    contrast: "#000000",
    accent: { primary: "#228DF2", shimmer: "#5B51EC" },
  },

  tokyonight: {
    text: { primary: "#C0CAF5", secondary: "#A9B1D6", muted: "#565F89", disabled: "#3B4261" },
    status: { success: "#9ECE6A", error: "#F7768E", warning: "#E0AF68", processing: "#7AA2F7", processingShimmer: "#BB9AF7" },
    selection: { active: "#7AA2F7", indicator: "#7AA2F7" },
    panel: { title: "#C0CAF5", subtitle: "#A9B1D6" },
    tabs: { active: "#7AA2F7", inactive: "#565F89", separator: "#292E42" },
    list: { itemText: "#C0CAF5", itemTextSelected: "#C0CAF5", itemDetail: "#565F89", scrollArrow: "#565F89" },
    keyValue: { label: "#C0CAF5", value: "#A9B1D6" },
    background: { base: "#1A1B26", panel: "#16161E", element: "#292E42", menu: "#292E42" },
    border: "#3B4261",
    divider: "#3B4261",
    footer: "#565F89",
    diff: { added: "#9ECE6A", addedBg: "#1A2D1A", removed: "#F7768E", removedBg: "#2D1A22" },
    tool: { pending: "#565F89", running: "#7AA2F7", completed: "#9ECE6A", error: "#F7768E" },
    contrast: "#000000",
    accent: { primary: "#7AA2F7", shimmer: "#BB9AF7" },
  },

  catppuccin: {
    text: { primary: "#CDD6F4", secondary: "#BAC2DE", muted: "#6C7086", disabled: "#45475A" },
    status: { success: "#A6E3A1", error: "#F38BA8", warning: "#FAB387", processing: "#89B4FA", processingShimmer: "#CBA6F7" },
    selection: { active: "#CBA6F7", indicator: "#CBA6F7" },
    panel: { title: "#CDD6F4", subtitle: "#BAC2DE" },
    tabs: { active: "#CBA6F7", inactive: "#6C7086", separator: "#313244" },
    list: { itemText: "#CDD6F4", itemTextSelected: "#CDD6F4", itemDetail: "#6C7086", scrollArrow: "#6C7086" },
    keyValue: { label: "#CDD6F4", value: "#BAC2DE" },
    background: { base: "#1E1E2E", panel: "#181825", element: "#313244", menu: "#313244" },
    border: "#45475A",
    divider: "#45475A",
    footer: "#6C7086",
    diff: { added: "#A6E3A1", addedBg: "#1A2D1E", removed: "#F38BA8", removedBg: "#2D1A22" },
    tool: { pending: "#6C7086", running: "#89B4FA", completed: "#A6E3A1", error: "#F38BA8" },
    contrast: "#000000",
    accent: { primary: "#CBA6F7", shimmer: "#F5C2E7" },
  },

  "catppuccin-latte": {
    text: { primary: "#4C4F69", secondary: "#6C6F85", muted: "#8C8FA1", disabled: "#ACB0BE" },
    status: { success: "#40A02B", error: "#D20F39", warning: "#FE640B", processing: "#1E66F5", processingShimmer: "#8839EF" },
    selection: { active: "#8839EF", indicator: "#8839EF" },
    panel: { title: "#4C4F69", subtitle: "#6C6F85" },
    tabs: { active: "#8839EF", inactive: "#8C8FA1", separator: "#CCD0DA" },
    list: { itemText: "#4C4F69", itemTextSelected: "#4C4F69", itemDetail: "#8C8FA1", scrollArrow: "#8C8FA1" },
    keyValue: { label: "#4C4F69", value: "#6C6F85" },
    background: { base: "#EFF1F5", panel: "#E6E9EF", element: "#CCD0DA", menu: "#CCD0DA" },
    border: "#BCC0CC",
    divider: "#BCC0CC",
    footer: "#8C8FA1",
    diff: { added: "#40A02B", addedBg: "#DFF3DB", removed: "#D20F39", removedBg: "#F3DBDF" },
    tool: { pending: "#8C8FA1", running: "#1E66F5", completed: "#40A02B", error: "#D20F39" },
    contrast: "#EFF1F5",
    accent: { primary: "#8839EF", shimmer: "#EA76CB" },
  },

  rosepine: {
    text: { primary: "#E0DEF4", secondary: "#908CAA", muted: "#6E6A86", disabled: "#524F67" },
    status: { success: "#9CCFD8", error: "#EB6F92", warning: "#F6C177", processing: "#C4A7E7", processingShimmer: "#EBBCBA" },
    selection: { active: "#C4A7E7", indicator: "#C4A7E7" },
    panel: { title: "#E0DEF4", subtitle: "#908CAA" },
    tabs: { active: "#C4A7E7", inactive: "#6E6A86", separator: "#26233A" },
    list: { itemText: "#E0DEF4", itemTextSelected: "#E0DEF4", itemDetail: "#6E6A86", scrollArrow: "#6E6A86" },
    keyValue: { label: "#E0DEF4", value: "#908CAA" },
    background: { base: "#191724", panel: "#1F1D2E", element: "#26233A", menu: "#26233A" },
    border: "#524F67",
    divider: "#524F67",
    footer: "#6E6A86",
    diff: { added: "#9CCFD8", addedBg: "#1A2D2D", removed: "#EB6F92", removedBg: "#2D1A22" },
    tool: { pending: "#6E6A86", running: "#C4A7E7", completed: "#9CCFD8", error: "#EB6F92" },
    contrast: "#000000",
    accent: { primary: "#EBBCBA", shimmer: "#F6C177" },
  },

  gruvbox: {
    text: { primary: "#EBDBB2", secondary: "#BDAE93", muted: "#928374", disabled: "#665C54" },
    status: { success: "#B8BB26", error: "#FB4934", warning: "#FE8019", processing: "#FABD2F", processingShimmer: "#83A598" },
    selection: { active: "#FE8019", indicator: "#FE8019" },
    panel: { title: "#EBDBB2", subtitle: "#BDAE93" },
    tabs: { active: "#FE8019", inactive: "#928374", separator: "#3C3836" },
    list: { itemText: "#EBDBB2", itemTextSelected: "#EBDBB2", itemDetail: "#928374", scrollArrow: "#928374" },
    keyValue: { label: "#EBDBB2", value: "#BDAE93" },
    background: { base: "#282828", panel: "#1D2021", element: "#3C3836", menu: "#3C3836" },
    border: "#504945",
    divider: "#504945",
    footer: "#928374",
    diff: { added: "#B8BB26", addedBg: "#2D3018", removed: "#FB4934", removedBg: "#3D1A18" },
    tool: { pending: "#928374", running: "#FABD2F", completed: "#B8BB26", error: "#FB4934" },
    contrast: "#000000",
    accent: { primary: "#FE8019", shimmer: "#FABD2F" },
  },

  dracula: {
    text: { primary: "#F8F8F2", secondary: "#BFBFBF", muted: "#6272A4", disabled: "#44475A" },
    status: { success: "#50FA7B", error: "#FF5555", warning: "#FFB86C", processing: "#BD93F9", processingShimmer: "#FF79C6" },
    selection: { active: "#BD93F9", indicator: "#BD93F9" },
    panel: { title: "#F8F8F2", subtitle: "#BFBFBF" },
    tabs: { active: "#BD93F9", inactive: "#6272A4", separator: "#44475A" },
    list: { itemText: "#F8F8F2", itemTextSelected: "#F8F8F2", itemDetail: "#6272A4", scrollArrow: "#6272A4" },
    keyValue: { label: "#F8F8F2", value: "#BFBFBF" },
    background: { base: "#282A36", panel: "#21222C", element: "#44475A", menu: "#44475A" },
    border: "#6272A4",
    divider: "#6272A4",
    footer: "#6272A4",
    diff: { added: "#50FA7B", addedBg: "#1A3D2A", removed: "#FF5555", removedBg: "#3D1A1A" },
    tool: { pending: "#6272A4", running: "#BD93F9", completed: "#50FA7B", error: "#FF5555" },
    contrast: "#000000",
    accent: { primary: "#BD93F9", shimmer: "#FF79C6" },
  },

  solarized: {
    text: { primary: "#93A1A1", secondary: "#839496", muted: "#657B83", disabled: "#586E75" },
    status: { success: "#859900", error: "#DC322F", warning: "#CB4B16", processing: "#268BD2", processingShimmer: "#6C71C4" },
    selection: { active: "#268BD2", indicator: "#268BD2" },
    panel: { title: "#93A1A1", subtitle: "#839496" },
    tabs: { active: "#268BD2", inactive: "#657B83", separator: "#073642" },
    list: { itemText: "#93A1A1", itemTextSelected: "#93A1A1", itemDetail: "#657B83", scrollArrow: "#657B83" },
    keyValue: { label: "#93A1A1", value: "#839496" },
    background: { base: "#002B36", panel: "#00242E", element: "#073642", menu: "#073642" },
    border: "#586E75",
    divider: "#586E75",
    footer: "#657B83",
    diff: { added: "#859900", addedBg: "#0A2E0A", removed: "#DC322F", removedBg: "#2E0A0A" },
    tool: { pending: "#657B83", running: "#268BD2", completed: "#859900", error: "#DC322F" },
    contrast: "#000000",
    accent: { primary: "#268BD2", shimmer: "#6C71C4" },
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
