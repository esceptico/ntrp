import { colors } from "../../../ui/index.js";

export function MaskedKeyInput({ value, cursor }: { value: string; cursor: number }) {
  const masked = value ? "\u2022".repeat(Math.min(value.length, 40)) : "";
  if (!value) {
    return (
      <text>
        <span fg={colors.text.muted}>paste key...</span>
        <span bg={colors.text.primary} fg={colors.contrast}>{" "}</span>
      </text>
    );
  }
  return (
    <text>
      <span fg={colors.text.primary}>{masked.slice(0, cursor)}</span>
      <span bg={colors.text.primary} fg={colors.contrast}>{masked[cursor] || " "}</span>
      <span fg={colors.text.primary}>{masked.slice(cursor + 1)}</span>
    </text>
  );
}
