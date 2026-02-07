import { Box, Text } from "ink";
import { Panel, Footer, colors, TextEditArea } from "../../ui/index.js";

interface ScheduleEditViewProps {
  editText: string;
  cursorPos: number;
  setEditText: (text: string | ((prev: string) => string)) => void;
  setCursorPos: (pos: number | ((prev: number) => number)) => void;
  saving: boolean;
  contentWidth: number;
}

export function ScheduleEditView({
  editText,
  cursorPos,
  setEditText,
  setCursorPos,
  saving,
  contentWidth,
}: ScheduleEditViewProps) {
  return (
    <Panel title="SCHEDULES" width={contentWidth}>
      <Box flexDirection="column" marginTop={1}>
        <Text color={colors.text.muted}>EDIT SCHEDULE DESCRIPTION</Text>
        <Box marginTop={1}>
          <TextEditArea
            value={editText}
            cursorPos={cursorPos}
            onValueChange={setEditText}
            onCursorChange={setCursorPos}
            placeholder="Type to edit..."
          />
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
