/**
 * macOS/iOS scroll-edge "progressive blur" — content blurs heavily at
 * the top of the scroll viewport and fades to clear below. Implemented
 * as 6 stacked sibling layers each with a different backdrop-filter
 * radius, masked to overlapping bands so the effective blur radius
 * varies smoothly along the strip. A single backdrop-filter + mask
 * can't do this — masks only control opacity of a uniformly-blurred
 * result, producing a hard-edged rectangle.
 *
 * Render as the FIRST child of a scrolling container; the sticky
 * positioning + negative margin-bottom keep it from consuming layout.
 *
 * Glass mode falls back to a pure opacity gradient because the modal
 * slab itself has backdrop-filter — stacking more inside would nest
 * (containing-block trap). Same fallback under
 * prefers-reduced-transparency / prefers-reduced-motion.
 *
 * Pattern + values: kennethnym.com/blog/progressive-blur-in-css and
 * devslovecoffee.com/blog/making-apple-progressive-blur-on-web.
 */
export function ScrollBlurTop() {
  return (
    <div aria-hidden className="scroll-blur-top">
      <div />
      <div />
      <div />
      <div />
      <div />
      <div />
    </div>
  );
}
