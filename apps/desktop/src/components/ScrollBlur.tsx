/**
 * Progressive blur for scroll-edge fading — content blurs heavily at
 * the top of the scroll viewport (where it meets the sticky chrome
 * above) and fades to perfectly clear below.
 *
 * Implementation follows Kenneth Nym's canonical recipe
 * (kennethnym.com/blog/progressive-blur-in-css) with a Skiper-UI-style
 * 8-layer stack:
 *   • 7 stacked `backdrop-filter` layers, blur radii double from 0.5px
 *     to 32px. Each layer is masked to a narrow visible band that
 *     overlaps its neighbors by ~50% so the effective blur radius
 *     varies smoothly along the strip.
 *   • Heavy-blur layer is the TOP of the strip (closest to the sticky
 *     header above); light-blur is the bottom.
 *   • An 8th layer on top is a solid `--color-bg` gradient that fades
 *     from bg-color at the top to transparent at the bottom. This
 *     hides the "blur abruptly ends" seam at the strip's top edge
 *     when content is scrolled past.
 *
 * Container has `pointer-events: none` and NO `border-radius` /
 * `overflow: hidden` (Chromium has known issues stacking
 * backdrop-filters inside a clipped wrapper).
 *
 * Glass mode: layered backdrop-filters would nest with the modal
 * slab's own filter (containing-block trap → visible stripes), so the
 * blur layers are inert and we fall back to just the bg-color gradient
 * cap. Same fallback under prefers-reduced-transparency /
 * prefers-reduced-motion.
 */
export function ScrollBlurTop() {
  return (
    <div aria-hidden className="scroll-blur-top">
      <div /><div /><div /><div /><div /><div /><div /><div />
    </div>
  );
}
