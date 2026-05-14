/**
 * Lucide icon size scale. One place for every `size={N}` in the app.
 *
 * Each tier corresponds to a visual role; pick by role, not by pixel.
 * Scale bumped 2025: at the previous sizes (11–14px) lucide icons
 * rendered as fuzzy threads on retina displays even at strokeWidth 1.8.
 * The new floor (13px) reads cleanly with the standard stroke width.
 *
 *   XS   (13) — tiny action buttons in tight rows (row hover icons,
 *               context-menu glyphs, search input chrome)
 *   SM   (14) — small chevrons, secondary action affordances
 *   MD   (16) — primary chrome icons (nav rows, header buttons,
 *               activity trace, send button)
 *   LG   (18) — emphasized icons (message actions, composer toolbar,
 *               skill chips when standalone)
 *   XL   (20) — large standalone glyphs (modal headers when prominent)
 *   HERO (24) — display-only, e.g. empty-state illustration
 *
 * Changing one value here ripples to every consumer.
 */
export const ICON = {
  XS: 13,
  SM: 14,
  MD: 16,
  LG: 18,
  XL: 20,
  HERO: 24,
} as const;
