import type { InputRenderable, TextareaRenderable } from "@opentui/core";
import { colors } from "../../ui/index.js";
import { CHECKBOX_CHECKED, CHECKBOX_UNCHECKED } from "../../../lib/constants.js";
import type { EditFocus } from "../../../hooks/useAutomations.js";
import type { NotifierSummary } from "../../../api/client.js";

interface AutomationEditViewProps {
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

export function AutomationEditView({
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
}: AutomationEditViewProps) {
  const LABEL_WIDTH = 14;
  const nameFocused = editFocus === "name";
  const descFocused = editFocus === "description";
  const notifFocused = editFocus === "notifiers";
  const selectedNotifierNames = availableNotifiers
    .filter((notifier) => editNotifiers.includes(notifier.name))
    .map((notifier) => notifier.name)
    .join(",");

  const labelCell = (text: string, focused: boolean) => (
    <box width={LABEL_WIDTH} flexShrink={0}>
      <text>
        <span fg={focused ? colors.selection.active : colors.text.disabled}>{focused ? ">" : " "}</span>
        <span fg={focused ? colors.text.primary : colors.text.muted}>{` ${text}`}</span>
      </text>
    </box>
  );

  return (
    <box flexDirection="column" width={width}>
      <box flexDirection="row">
        {labelCell("NAME", nameFocused)}
        <input
          ref={nameRef}
          value={editName}
          placeholder="automation name"
          focused={nameFocused}
          textColor={colors.text.primary}
          focusedTextColor={colors.text.primary}
          cursorColor={colors.text.primary}
          showCursor={nameFocused}
          width={Math.max(8, width - LABEL_WIDTH)}
        />
      </box>

      <box flexDirection="row">
        {labelCell("DESCRIPTION", descFocused)}
        <box flexGrow={1}>
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
            maxHeight={6}
            width={Math.max(8, width - LABEL_WIDTH)}
          />
        </box>
      </box>

      {availableNotifiers.length > 0 && (
        <>
          <box flexDirection="row">
            {labelCell("NOTIFIERS", notifFocused)}
            <text><span fg={colors.text.muted}>select targets</span></text>
          </box>
          <box flexDirection="column">
            {availableNotifiers.map((notifier, idx) => {
              const isCursor = notifFocused && idx === editNotifierCursor;
              const isChecked = editNotifiers.includes(notifier.name);
              return (
                <box key={notifier.name} flexDirection="row">
                  <box width={LABEL_WIDTH} />
                  <text>
                    <span fg={isCursor ? colors.selection.active : colors.text.disabled}>{isCursor ? ">" : " "}</span>
                    <span fg={isChecked ? colors.status.success : colors.text.disabled}>{` ${isChecked ? CHECKBOX_CHECKED : CHECKBOX_UNCHECKED} `}</span>
                    <span fg={isCursor ? colors.text.primary : colors.text.secondary}>{notifier.name}</span>
                    <span fg={colors.text.muted}>{` (${notifier.type})`}</span>
                  </text>
                </box>
              );
            })}
          </box>
        </>
      )}

      <box flexDirection="row">
        {labelCell("PREVIEW", false)}
        <text><span fg={colors.text.secondary}>{`Edit name/description -> ${selectedNotifierNames || "none"}`}</span></text>
      </box>

      {saving && (
        <box marginTop={1}>
          <text><span fg={colors.tool.running}>Saving...</span></text>
        </box>
      )}
    </box>
  );
}
