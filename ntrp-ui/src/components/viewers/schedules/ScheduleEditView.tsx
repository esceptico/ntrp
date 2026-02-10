import { Box, Text } from "ink";
import { Panel, Footer, colors, TextEditArea } from "../../ui/index.js";
import { CHECKBOX_CHECKED, CHECKBOX_UNCHECKED } from "../../../lib/constants.js";
import type { EditFocus } from "../../../hooks/useSchedules.js";

interface ScheduleEditViewProps {
  editText: string;
  cursorPos: number;
  setEditText: (text: string | ((prev: string) => string)) => void;
  setCursorPos: (pos: number | ((prev: number) => number)) => void;
  saving: boolean;
  contentWidth: number;
  editFocus: EditFocus;
  availableNotifiers: string[];
  editNotifiers: string[];
  editNotifierCursor: number;
}

export function ScheduleEditView({
  editText,
  cursorPos,
  setEditText,
  setCursorPos,
  saving,
  contentWidth,
  editFocus,
  availableNotifiers,
  editNotifiers,
  editNotifierCursor,
}: ScheduleEditViewProps) {
  const descFocused = editFocus === "description";
  const notifFocused = editFocus === "notifiers";

  return (
    <Panel title="SCHEDULES" width={contentWidth}>
      <Box flexDirection="column" marginTop={1}>
        <Text color={descFocused ? colors.text.primary : colors.text.muted} bold={descFocused}>DESCRIPTION</Text>
        <Box marginTop={1}>
          <TextEditArea
            value={editText}
            cursorPos={cursorPos}
            onValueChange={setEditText}
            onCursorChange={setCursorPos}
            placeholder="Type to edit..."
            showCursor={descFocused}
          />
        </Box>

        {availableNotifiers.length > 0 && (
          <>
            <Box marginTop={1}>
              <Text color={notifFocused ? colors.text.primary : colors.text.muted} bold={notifFocused}>NOTIFIERS</Text>
            </Box>
            <Box flexDirection="column" marginTop={1}>
              {availableNotifiers.map((name, idx) => {
                const isCursor = notifFocused && idx === editNotifierCursor;
                const isChecked = editNotifiers.includes(name);
                return (
                  <Text key={name}>
                    <Text color={isCursor ? colors.selection.active : colors.text.disabled}>{isCursor ? "› " : "  "}</Text>
                    <Text color={isChecked ? colors.status.success : colors.text.disabled}>{isChecked ? CHECKBOX_CHECKED : CHECKBOX_UNCHECKED}</Text>
                    <Text color={isCursor ? colors.text.primary : colors.text.secondary}>{name}</Text>
                  </Text>
                );
              })}
            </Box>
          </>
        )}

        {saving && (
          <Box marginTop={1}>
            <Text color={colors.tool.running}>Saving...</Text>
          </Box>
        )}
      </Box>
      <Footer>
        {saving ? "Saving..." : `Ctrl+S: save  Esc: cancel${availableNotifiers.length > 0 ? "  Tab: switch section" : ""}  space: toggle`}
      </Footer>
    </Panel>
  );
}
