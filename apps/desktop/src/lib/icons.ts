/**
 * Lucide icon size scale. One place for every `size={N}` in the app.
 *
 * Each tier corresponds to a visual role; pick by role, not by pixel:
 *   XS  (11) — tiny action buttons in tight rows (row hover icons,
 *              context-menu glyphs, search input chrome)
 *   SM  (12) — small chevrons, secondary action affordances
 *   MD  (13) — primary chrome icons (nav rows, header buttons,
 *              activity trace, send button)
 *   LG  (14) — emphasized icons (message actions, composer toolbar,
 *              skill chips when standalone)
 *   XL  (16) — large standalone glyphs (modal headers when prominent)
 *   HERO (20) — display-only, e.g. empty-state illustration
 *
 * Changing one value here ripples to every consumer.
 */
export const ICON = {
  XS: 11,
  SM: 12,
  MD: 13,
  LG: 14,
  XL: 16,
  HERO: 20,
} as const;
