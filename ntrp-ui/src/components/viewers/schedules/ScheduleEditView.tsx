import type { InputRenderable, TextareaRenderable } from "@opentui/core";
import { colors } from "../../ui/index.js";
import { CHECKBOX_CHECKED, CHECKBOX_UNCHECKED } from "../../../lib/constants.js";
import type { EditFocus } from "../../../hooks/useSchedules.js";
import type { NotifierSummary } from "../../../api/client.js";

interface ScheduleEditViewProps {
  editName: string;
  editText: string;
  saving: boolean;
  width: number;
  editFocus: EditFocus;
  availableNotifiers: NotifierSummary[];
  editNotifiers: string[];
  editNotifierCursor: number;
  nameRef: (r: InputRenderable) => void;
  descRef: (r: TextareaRenderable) => void;
}

export function ScheduleEditView({
  editName,
  editText,
  saving,
  width,
  editFocus,
  availableNotifiers,
  editNotifiers,
  editNotifierCursor,
  nameRef,
  descRef,
}: ScheduleEditViewProps) {
  const nameFocused = editFocus === "name";
  const descFocused = editFocus === "description";
  const notifFocused = editFocus === "notifiers";

  return (
    <box flexDirection="column" width={width}>
      <text>
        {nameFocused
          ? <span fg={colors.text.primary}><strong>NAME</strong></span>
          : <span fg={colors.text.muted}>NAME</span>
        }
      </text>
      <box marginTop={1}>
        <input
          ref={nameRef}
          value={editName}
          placeholder="schedule name"
          focused={nameFocused}
          textColor={colors.text.primary}
          focusedTextColor={colors.text.primary}
          cursorColor={colors.text.primary}
          showCursor={nameFocused}
          width={width}
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
        <textarea
          ref={descRef}
          initialValue={editText}
          placeholder="Type to edit..."
          focused={descFocused}
          textColor={colors.text.primary}
          focusedTextColor={colors.text.primary}
          cursorColor={colors.text.primary}
          placeholderColor={colors.text.muted}
          showCursor={descFocused}
          wrapMode="word"
          minHeight={1}
          maxHeight={10}
          width={width}
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
            {availableNotifiers.map((notifier, idx) => {
              const isCursor = notifFocused && idx === editNotifierCursor;
              const isChecked = editNotifiers.includes(notifier.name);
              return (
                <text key={notifier.name}>
                  <span fg={isCursor ? colors.selection.active : colors.text.disabled}>{isCursor ? "\u203A " : "  "}</span>
                  <span fg={isChecked ? colors.status.success : colors.text.disabled}>{isChecked ? CHECKBOX_CHECKED : CHECKBOX_UNCHECKED}</span>
                  <span fg={isCursor ? colors.text.primary : colors.text.secondary}>{notifier.name}</span>
                  <span fg={colors.text.muted}>{` (${notifier.type})`}</span>
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
  );
}
