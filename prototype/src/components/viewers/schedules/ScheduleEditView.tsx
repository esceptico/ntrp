import { Panel, Footer, colors, TextEditArea, TextInputField } from "../../ui/index.js";
import { CHECKBOX_CHECKED, CHECKBOX_UNCHECKED } from "../../../lib/constants.js";
import type { EditFocus } from "../../../hooks/useSchedules.js";

interface ScheduleEditViewProps {
  editName: string;
  editNameCursorPos: number;
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
  editName,
  editNameCursorPos,
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
  const nameFocused = editFocus === "name";
  const descFocused = editFocus === "description";
  const notifFocused = editFocus === "notifiers";

  return (
    <Panel title="SCHEDULES" width={contentWidth}>
      <box flexDirection="column" marginTop={1}>
        <text>
          {nameFocused
            ? <span fg={colors.text.primary}><strong>NAME</strong></span>
            : <span fg={colors.text.muted}>NAME</span>
          }
        </text>
        <box marginTop={1}>
          <TextInputField
            value={editName}
            cursorPos={editNameCursorPos}
            placeholder="schedule name"
            showCursor={nameFocused}
          />
        </box>

        <box marginTop={1}>
          <text>
            {descFocused
              ? <span fg={colors.text.primary}><strong>DESCRIPTION</strong></span>
              : <span fg={colors.text.muted}>DESCRIPTION</span>
            }
          </text>
        </box>
        <box marginTop={1}>
          <TextEditArea
            value={editText}
            cursorPos={cursorPos}
            onValueChange={setEditText}
            onCursorChange={setCursorPos}
            placeholder="Type to edit..."
            showCursor={descFocused}
          />
        </box>

        {availableNotifiers.length > 0 && (
          <>
            <box marginTop={1}>
              <text>
                {notifFocused
                  ? <span fg={colors.text.primary}><strong>NOTIFIERS</strong></span>
                  : <span fg={colors.text.muted}>NOTIFIERS</span>
                }
              </text>
            </box>
            <box flexDirection="column" marginTop={1}>
              {availableNotifiers.map((name, idx) => {
                const isCursor = notifFocused && idx === editNotifierCursor;
                const isChecked = editNotifiers.includes(name);
                return (
                  <text key={name}>
                    <span fg={isCursor ? colors.selection.active : colors.text.disabled}>{isCursor ? "\u203A " : "  "}</span>
                    <span fg={isChecked ? colors.status.success : colors.text.disabled}>{isChecked ? CHECKBOX_CHECKED : CHECKBOX_UNCHECKED}</span>
                    <span fg={isCursor ? colors.text.primary : colors.text.secondary}>{name}</span>
                  </text>
                );
              })}
            </box>
          </>
        )}

        {saving && (
          <box marginTop={1}>
            <text><span fg={colors.tool.running}>Saving...</span></text>
          </box>
        )}
      </box>
      <Footer>
        {saving ? "Saving..." : "Ctrl+S: save  Esc: cancel  Tab: next section"}
      </Footer>
    </Panel>
  );
}
