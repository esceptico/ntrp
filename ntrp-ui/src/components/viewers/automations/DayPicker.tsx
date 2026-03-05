import { colors } from "../../ui/index.js";
import { DAY_NAMES, type CreateFocus } from "./AutomationCreateView.js";
import { LABEL_WIDTH, labelCell, dayCell } from "./FormHelpers.js";

export interface DayPickerProps {
  focus: CreateFocus;
  editing: boolean;
  customDays: string[];
  dayCursor: number;
}

export function DayPicker({ focus, editing, customDays, dayCursor }: DayPickerProps) {
  return (
    <>
      <box flexDirection="row">
        {labelCell("PICK", focus === "day_picker")}
        <box flexDirection="row" flexWrap="wrap">
          {DAY_NAMES.map((day, idx) => {
            const isSelected = customDays.includes(day);
            const isCursor = editing && focus === "day_picker" && idx === dayCursor;
            return dayCell(day, isSelected, isCursor);
          })}
        </box>
        {focus === "day_picker" && !editing && <text><span fg={colors.text.muted}> enter to edit</span></text>}
      </box>
      <box flexDirection="row">
        <box width={LABEL_WIDTH} />
        <text>
          <span fg={colors.text.muted}>Selected: </span>
          <span fg={customDays.length > 0 ? colors.status.success : colors.text.disabled}>
            {customDays.length > 0 ? customDays.join(", ") : "none (space to toggle)"}
          </span>
        </text>
      </box>
    </>
  );
}
