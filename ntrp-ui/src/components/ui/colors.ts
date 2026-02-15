/**
 * NTRP Color System — dark/light bases + mono accent variations.
 *
 * Adding an accent: add an entry to `accents`.
 * Everything else (setTheme, /theme command, settings) picks it up automatically.
 */

export type AccentColor = "gray";

type Palette = {
  text: { primary: string; secondary: string; muted: string; disabled: string };
  status: { success: string; error: string; warning: string; processing: string; processingShimmer: string };
  selection: { active: string; indicator: string };
  panel: { title: string; subtitle: string };
  tabs: { active: string; inactive: string; separator: string };
  list: { itemText: string; itemTextSelected: string; itemDetail: string; scrollArrow: string };
  keyValue: { label: string; value: string };
  background: { base: string; panel: string; element: string; menu: string };
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
    text: { primary: "#c8c8c8", secondary: "#888888", muted: "#6a6a6a", disabled: "#505050" },
    status: { success: "#888888", error: "#888888", warning: "#888888", processing: "#c8c8c8", processingShimmer: "#e0e0e0" },
    selection: { active: "#c8c8c8", indicator: "#c8c8c8" },
    panel: { title: "#c8c8c8", subtitle: "#888888" },
    tabs: { active: "#c8c8c8", inactive: "#6a6a6a", separator: "#3a3a3a" },
    list: { itemText: "#c8c8c8", itemTextSelected: "#c8c8c8", itemDetail: "#6a6a6a", scrollArrow: "#6a6a6a" },
    keyValue: { label: "#c8c8c8", value: "#888888" },
    background: { base: "#181818", panel: "#101010", element: "#2c2c2c", menu: "#2c2c2c" },
    border: "#3a3a3a",
    divider: "#3a3a3a",
    footer: "#6a6a6a",
    diff: { added: "#888888", addedBg: "#2c2c2c", removed: "#6a6a6a", removedBg: "#212121" },
    tool: { pending: "#6a6a6a", running: "#888888", completed: "#c8c8c8", error: "#888888" },
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

// -- Accent colors ----------------------------------------------------------

const accents = {
  blue:   { dark: { primary: "#7aa2f7", shimmer: "#82aaff" }, light: { primary: "#3b6dd4", shimmer: "#5a88e0" } },
  cyan:   { dark: { primary: "#88c0d0", shimmer: "#8fbcbb" }, light: { primary: "#2a8a9a", shimmer: "#3d9eab" } },
  green:  { dark: { primary: "#8ec07c", shimmer: "#a7c080" }, light: { primary: "#4a8a3e", shimmer: "#5c9e4e" } },
  purple: { dark: { primary: "#b4befe", shimmer: "#c4a7e7" }, light: { primary: "#7b5ebd", shimmer: "#9070d0" } },
  rose:   { dark: { primary: "#ebbcba", shimmer: "#f5c2e7" }, light: { primary: "#c06070", shimmer: "#d07585" } },
  amber:  { dark: { primary: "#e6b450", shimmer: "#ffb454" }, light: { primary: "#b08520", shimmer: "#c49830" } },
  red:    { dark: { primary: "#e06c75", shimmer: "#f07080" }, light: { primary: "#c04048", shimmer: "#d05058" } },
} as const;

type AccentName = keyof typeof accents;
type BaseName = keyof typeof bases;

// -- Generate palettes: base + base-accent combos ---------------------------

function withAccent(base: Palette, accent: { primary: string; shimmer: string }): Palette {
  return {
    ...base,
    selection: { active: accent.primary, indicator: accent.primary },
    accent,
  };
}

const palettes: Record<string, Palette> = {};

for (const baseName of Object.keys(bases) as BaseName[]) {
  // plain base (no accent color)
  palettes[baseName] = bases[baseName];
  // accented variants
  for (const accentName of Object.keys(accents) as AccentName[]) {
    palettes[`${baseName}-${accentName}`] = withAccent(bases[baseName], accents[accentName][baseName]);
  }
}

export { palettes };
export type Theme = string;
export const themeNames = Object.keys(palettes);

// -- Exports (mutated in place by setTheme) ---------------------------------

export const accentColors = { gray: { ...palettes.dark.accent } };

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

let currentAccent: AccentColor = "gray";

export function syncAccentColor(color: AccentColor) {
  currentAccent = color;
}

export function setTheme(theme: Theme) {
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
  colors.border = p.border;
  colors.divider = p.divider;
  colors.footer = p.footer;
  Object.assign(colors.diff, p.diff);
  Object.assign(colors.tool, p.tool);
  colors.contrast = p.contrast;
  Object.assign(accentColors.gray, p.accent);
}
