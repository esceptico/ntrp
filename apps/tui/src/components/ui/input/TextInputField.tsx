import { colors } from "../colors.js";

interface TextInputFieldProps {
  value: string;
  cursorPos: number;
  placeholder?: string;
  showCursor?: boolean;
  placeholderColor?: string;
  textColor?: string;
}

export function TextInputField({
  value,
  cursorPos,
  placeholder = "",
  showCursor = true,
  placeholderColor = colors.text.muted,
  textColor = colors.text.primary,
}: TextInputFieldProps) {
  if (value) {
    if (showCursor) {
      const beforeCursor = value.slice(0, cursorPos);
      const atCursor = value[cursorPos] || " ";
      const afterCursor = value.slice(cursorPos + 1);
      return (
        <text>
          <span fg={textColor}>{beforeCursor}</span>
          <span bg={colors.text.primary} fg={colors.contrast}>{atCursor}</span>
          <span fg={textColor}>{afterCursor}</span>
        </text>
      );
    }
    return (
      <text><span fg={textColor}>{value}</span></text>
    );
  }

  return (
    <text>
      <span fg={placeholderColor}>{placeholder}</span>
      {showCursor && <span bg={colors.text.primary} fg={colors.contrast}>{" "}</span>}
    </text>
  );
}
