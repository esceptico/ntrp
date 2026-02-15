import { colors } from "./colors.js";

interface TextEditAreaProps {
  value: string;
  cursorPos: number;
  onValueChange: (value: string | ((prev: string) => string)) => void;
  onCursorChange: (pos: number | ((prev: number) => number)) => void;
  placeholder?: string;
  showCursor?: boolean;
}

export function TextEditArea({
  value,
  cursorPos,
  placeholder = "Type to edit...",
  showCursor = true,
}: TextEditAreaProps) {
  const lines = value.split("\n");
  let charCount = 0;
  let cursorLine = 0;
  let cursorCol = 0;

  for (let i = 0; i < lines.length; i++) {
    const lineLength = lines[i].length + 1;
    if (charCount + lineLength > cursorPos) {
      cursorLine = i;
      cursorCol = cursorPos - charCount;
      break;
    }
    charCount += lineLength;
  }

  return (
    <box flexDirection="column">
      {lines.length === 0 || (lines.length === 1 && lines[0] === "") ? (
        <text>
          <span fg={colors.text.muted}>{placeholder}</span>
          {showCursor && <span bg={colors.text.primary} fg={colors.contrast}> </span>}
        </text>
      ) : (
        lines.map((line, idx) => {
          if (showCursor && idx === cursorLine) {
            const beforeCursor = line.slice(0, cursorCol);
            const atCursor = line[cursorCol] || " ";
            const afterCursor = line.slice(cursorCol + 1);
            return (
              <text key={idx}>
                <span fg={colors.text.primary}>{beforeCursor}</span>
                <span bg={colors.text.primary} fg={colors.contrast}>{atCursor}</span>
                <span fg={colors.text.primary}>{afterCursor}</span>
              </text>
            );
          }
          return (
            <text key={idx}>
              <span fg={colors.text.primary}>{line || " "}</span>
            </text>
          );
        })
      )}
    </box>
  );
}
