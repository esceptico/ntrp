import { Box, Text } from "ink";
import { colors } from "./colors.js";

interface TextEditAreaProps {
  value: string;
  cursorPos: number;
  onValueChange: (value: string | ((prev: string) => string)) => void;
  onCursorChange: (pos: number | ((prev: number) => number)) => void;
  placeholder?: string;
}

/**
 * Reusable multi-line text input with cursor support
 * Based on chat input rendering, displays text with cursor
 */
export function TextEditArea({
  value,
  cursorPos,
  onValueChange,
  onCursorChange,
  placeholder = "Type to edit...",
}: TextEditAreaProps) {

  // Simple cursor rendering - just like chat input
  const lines = value.split("\n");
  let charCount = 0;
  let cursorLine = 0;
  let cursorCol = 0;

  for (let i = 0; i < lines.length; i++) {
    const lineLength = lines[i].length + 1; // +1 for newline
    if (charCount + lineLength > cursorPos) {
      cursorLine = i;
      cursorCol = cursorPos - charCount;
      break;
    }
    charCount += lineLength;
  }

  return (
    <Box flexDirection="column">
      {lines.length === 0 || (lines.length === 1 && lines[0] === "") ? (
        <Text color={colors.text.muted}>
          {placeholder}
          <Text inverse> </Text>
        </Text>
      ) : (
        lines.map((line, idx) => {
          if (idx === cursorLine) {
            const beforeCursor = line.slice(0, cursorCol);
            const atCursor = line[cursorCol] || " ";
            const afterCursor = line.slice(cursorCol + 1);
            return (
              <Text key={idx} color={colors.text.primary}>
                <Text>{beforeCursor}</Text>
                <Text inverse>{atCursor}</Text>
                <Text>{afterCursor}</Text>
              </Text>
            );
          }
          return (
            <Text key={idx} color={colors.text.primary}>
              {line || " "}
            </Text>
          );
        })
      )}
    </Box>
  );
}
