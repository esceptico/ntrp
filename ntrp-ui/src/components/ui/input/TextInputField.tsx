import { Text } from "ink";
import { colors } from "../colors.js";
import { CURSOR_CHAR } from "../../../lib/constants.js";

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
    return (
      <Text color={textColor}>
        {value.slice(0, cursorPos)}
        {showCursor && CURSOR_CHAR}
        {value.slice(cursorPos)}
      </Text>
    );
  }

  return (
    <Text color={placeholderColor}>
      {placeholder}
      {showCursor && CURSOR_CHAR}
    </Text>
  );
}
