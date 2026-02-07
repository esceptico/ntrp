import { Box, Text } from "ink";
import { Panel, Footer, colors } from "../../ui/index.js";
import { useAccentColor } from "../../../hooks/index.js";
import { wrapText } from "../../../lib/utils.js";

interface ScheduleEditViewProps {
  editText: string;
  cursorPos: number;
  saving: boolean;
  contentWidth: number;
  textWidth: number;
}

export function ScheduleEditView({
  editText,
  cursorPos,
  saving,
  contentWidth,
  textWidth,
}: ScheduleEditViewProps) {
  const { accentValue } = useAccentColor();
  const wrappedLines = wrapText(editText, textWidth);
  let charCount = 0;
  let cursorLine = 0;
  let cursorCol = 0;

  if (wrappedLines.length === 0) {
    cursorLine = 0;
    cursorCol = 0;
  } else {
    for (let i = 0; i < wrappedLines.length; i++) {
      const lineLength = wrappedLines[i].length;
      if (charCount + lineLength >= cursorPos) {
        cursorLine = i;
        cursorCol = cursorPos - charCount;
        break;
      }
      charCount += lineLength;
    }
    if (cursorPos === editText.length && cursorPos > charCount) {
      cursorLine = wrappedLines.length - 1;
      cursorCol = wrappedLines[cursorLine].length;
    }
  }

  return (
    <Panel title="SCHEDULES" width={contentWidth}>
      <Box flexDirection="column" marginTop={1}>
        <Text color={colors.text.muted}>EDIT SCHEDULE DESCRIPTION</Text>
        <Box marginTop={1} flexDirection="column">
          {wrappedLines.length === 0 ? (
            <Text color={colors.text.muted}>
              Type to edit...
              <Text color={accentValue}>█</Text>
            </Text>
          ) : (
            wrappedLines.map((line, idx) => (
              <Text key={idx} color={colors.text.primary}>
                {idx === cursorLine ? (
                  <>
                    {line.slice(0, cursorCol)}
                    <Text color={accentValue}>█</Text>
                    {line.slice(cursorCol)}
                  </>
                ) : (
                  line
                )}
              </Text>
            ))
          )}
        </Box>
        {saving && (
          <Box marginTop={1}>
            <Text color={colors.tool.running}>Saving...</Text>
          </Box>
        )}
      </Box>
      <Footer>
        {saving ? "Saving..." : "Ctrl+S: save │ Esc: cancel │ ←→: move cursor │ Home/End: start/end"}
      </Footer>
    </Panel>
  );
}
