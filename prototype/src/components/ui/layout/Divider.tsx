import { useContentWidth } from "../../../contexts/index.js";
import { colors } from "../colors.js";

interface DividerProps {
  width?: number;
}

export function Divider({ width }: DividerProps) {
  const contentWidth = useContentWidth();
  const lineWidth = width ?? Math.min(contentWidth - 2, 60);
  const line = "\u2500".repeat(Math.max(0, lineWidth));

  return <text><span fg={colors.divider}>{line}</span></text>;
}
