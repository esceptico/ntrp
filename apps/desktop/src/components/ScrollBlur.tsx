/**
 * Short, subtle scroll-edge blur — content blurs softly through a
 * ~32px sticky band at the top of the scroll viewport. Modeled on
 * macOS Safari's toolbar and iOS Settings header behavior: a single
 * thin translucent bar with mild backdrop-filter and a gradient mask
 * that fades the blur effect out at the bottom.
 *
 * Not the "progressive blur" hero-section effect (Kenneth Nym / Skiper-UI
 * recipe). That's for 100-200px decorative reveals and produces a
 * visible "blur zone" — wrong for tight modal chrome.
 *
 * Linen-mode only. Glass mode falls through to nothing (the modal
 * slab's own backdrop-filter takes care of context separation).
 * prefers-reduced-* respected via CSS.
 */
export function ScrollBlurTop() {
  return <div aria-hidden className="scroll-blur-top" />;
}
