import { colors } from "../../ui/index.js";
import { CHECKBOX_CHECKED, CHECKBOX_UNCHECKED } from "../../../lib/constants.js";
import type { NotifierSummary } from "../../../api/client.js";
import type { CreateFocus } from "./AutomationCreateView.js";
import { LABEL_WIDTH, labelCell } from "./FormHelpers.js";

export interface NotifierSelectorProps {
  focus: CreateFocus;
  editing: boolean;
  availableNotifiers: NotifierSummary[];
  notifiers: string[];
  notifierCursor: number;
}

export function NotifierSelector({ focus, editing, availableNotifiers, notifiers, notifierCursor }: NotifierSelectorProps) {
  return (
    <>
      <box flexDirection="row">
        {labelCell("NOTIFIERS", focus === "notifiers")}
        <text><span fg={colors.text.muted}>select targets</span></text>
        {focus === "notifiers" && !editing && <text><span fg={colors.text.muted}> enter to edit</span></text>}
      </box>
      <box flexDirection="column">
        {availableNotifiers.map((notifier, idx) => {
          const isCursor = editing && focus === "notifiers" && idx === notifierCursor;
          const isChecked = notifiers.includes(notifier.name);
          return (
            <box key={notifier.name} flexDirection="row">
              <box width={LABEL_WIDTH} />
              <text>
                <span fg={isCursor ? colors.selection.active : colors.text.disabled}>{isCursor ? ">" : " "}</span>
                <span fg={isChecked ? colors.status.success : colors.text.disabled}>{` ${isChecked ? CHECKBOX_CHECKED : CHECKBOX_UNCHECKED} `}</span>
                <span fg={isCursor ? colors.text.primary : colors.text.secondary}>{notifier.name}</span>
                <span fg={colors.text.muted}>{` (${notifier.type}) -> ${isChecked ? "configured" : "add..."}`}</span>
              </text>
            </box>
          );
        })}
      </box>
    </>
  );
}
