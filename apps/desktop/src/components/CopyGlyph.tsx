import { Check, Copy } from "lucide-react";
import { BlurSwap } from "./BlurSwap";

/**
 * The Copy → Check glyph swap shared by every copy button in the app
 * (messages, code blocks, tool output, diagrams). Wrapping the swap in
 * BlurSwap means the flash-to-checkmark crossfades in place instead of
 * hard-cutting. Button chrome + clipboard logic stay at each call site —
 * only the icon swap is shared, since those legitimately differ.
 */
export function CopyGlyph({
  copied,
  size,
  checkClassName,
}: {
  copied: boolean;
  size: number;
  /** Applied to the Check only — for sites that tint the success glyph. */
  checkClassName?: string;
}) {
  return (
    <BlurSwap swapKey={copied ? "check" : "copy"} blur={3}>
      {copied ? (
        <Check size={size} strokeWidth={2.4} className={checkClassName} />
      ) : (
        <Copy size={size} strokeWidth={2} />
      )}
    </BlurSwap>
  );
}
