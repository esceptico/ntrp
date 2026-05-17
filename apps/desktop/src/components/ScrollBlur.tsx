/**
 * Real backdrop-filter blur band pinned to the top edge of a scroll
 * container — content actually blurs as it scrolls under sticky
 * chrome (macOS/iOS scroll-edge behavior), not just opacity-fades.
 *
 * Must be the FIRST child of the scroll container. Sticky + negative
 * margin-bottom keeps it from consuming layout space. Per-material
 * blur strength is handled in `.scroll-blur-top` CSS so we don't
 * double-blur inside Glass-mode slabs.
 */
export function ScrollBlurTop() {
  return <div aria-hidden className="scroll-blur-top" />;
}
