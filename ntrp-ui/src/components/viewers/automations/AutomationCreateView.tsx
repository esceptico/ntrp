import { colors, TextInputField, TextEditArea } from "../../ui/index.js";
import { CHECKBOX_CHECKED, CHECKBOX_UNCHECKED } from "../../../lib/constants.js";
import type { NotifierSummary } from "../../../api/client.js";

export type CreateFocus = "name" | "description" | "model" | "trigger_type" | "mode" | "time" | "interval" | "start" | "end" | "days" | "day_picker" | "event_type" | "event_lead" | "notifiers" | "writable";

export const TRIGGER_TYPES = ["time", "event"] as const;
export const SCHEDULE_MODES = ["schedule", "interval"] as const;
export const SCHEDULE_DAYS = ["once", "daily", "weekdays", "custom"] as const;
export const INTERVAL_DAYS = ["always", "weekdays", "custom"] as const;
export const EVENT_TYPES = ["event_approaching"] as const;
export const DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;

interface AutomationCreateViewProps {
  focus: CreateFocus;
  triggerType: "time" | "event";
  scheduleMode: "schedule" | "interval";
  daysOption: string;
  eventType: string;
  writable: boolean;
  saving: boolean;
  error: string | null;
  width: number;
  availableNotifiers: NotifierSummary[];
  notifiers: string[];
  notifierCursor: number;
  customDays: string[];
  dayCursor: number;
  nameValue: string;
  nameCursorPos: number;
  descValue: string;
  descCursorPos: number;
  selectedModel: string;
  eventLeadValue: string;
  eventLeadCursorPos: number;
  timeValue: string;
  timeCursorPos: number;
  intervalValue: string;
  intervalCursorPos: number;
  startValue: string;
  startCursorPos: number;
  endValue: string;
  endCursorPos: number;
  canSave: boolean;
}

export function AutomationCreateView({
  focus,
  triggerType,
  scheduleMode,
  daysOption,
  eventType,
  writable,
  saving,
  error,
  width,
  availableNotifiers,
  notifiers,
  notifierCursor,
  customDays,
  dayCursor,
  nameValue,
  nameCursorPos,
  descValue,
  descCursorPos,
  selectedModel,
  eventLeadValue,
  eventLeadCursorPos,
  timeValue,
  timeCursorPos,
  intervalValue,
  intervalCursorPos,
  startValue,
  startCursorPos,
  endValue,
  endCursorPos,
  canSave,
}: AutomationCreateViewProps) {
  const LABEL_WIDTH = 14;

  const parseHmToMinutes = (value: string): number | null => {
    const m = /^(\d{1,2}):(\d{2})$/.exec(value.trim());
    if (!m) return null;
    const hours = Number(m[1]);
    const mins = Number(m[2]);
    if (hours < 0 || hours > 23 || mins < 0 || mins > 59) return null;
    return (hours * 60) + mins;
  };

  const renderWindowBar = (start: string, end: string): string => {
    const slots = 32;
    const startMins = parseHmToMinutes(start);
    const endMins = parseHmToMinutes(end);
    if (startMins === null || endMins === null || endMins <= startMins) {
      return "|--------------------------------|";
    }
    const startIdx = Math.max(0, Math.min(slots - 1, Math.floor((startMins / 1440) * slots)));
    const endIdx = Math.max(startIdx + 1, Math.min(slots, Math.ceil((endMins / 1440) * slots)));
    let bar = "|";
    for (let i = 0; i < slots; i++) {
      bar += i >= startIdx && i < endIdx ? "█" : "-";
    }
    bar += "|";
    return bar;
  };

  const labelCell = (text: string, focused: boolean) => (
    <box width={LABEL_WIDTH} flexShrink={0}>
      <text>
        <span fg={focused ? colors.selection.active : colors.text.disabled}>{focused ? ">" : " "}</span>
        <span fg={focused ? colors.text.primary : colors.text.muted}>{` ${text}`}</span>
      </text>
    </box>
  );

  const optionCell = (opt: string, selected: boolean, focused: boolean) => {
    const fg = selected
      ? (focused ? colors.text.primary : colors.text.secondary)
      : colors.text.disabled;
    return (
      <text key={opt}>
        <span fg={fg}>{selected ? `[${opt}]` : ` ${opt} `}</span>
      </text>
    );
  };

  /** Day picker: selected = filled circle, unselected = empty circle. Unmistakable. */
  const dayCell = (day: string, isSelected: boolean, isCursor: boolean) => {
    const marker = isSelected ? "\u25CF" : "\u25CB"; // ● vs ○
    const fg = isSelected
      ? (isCursor ? colors.selection.active : colors.status.success)
      : (isCursor ? colors.text.primary : colors.text.disabled);
    return (
      <text key={day}>
        <span fg={fg}>{` ${marker} ${day} `}</span>
      </text>
    );
  };

  const selectorRow = (label: string, focused: boolean, options: readonly string[], selected: string) => (
    <box flexDirection="row">
      {labelCell(label, focused)}
      <box flexDirection="row" flexWrap="wrap">
        {options.map((opt) => optionCell(opt, opt === selected, focused))}
      </box>
    </box>
  );

  const daysOptions = scheduleMode === "schedule" ? SCHEDULE_DAYS : INTERVAL_DAYS;
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const activeNotifiers = availableNotifiers.filter((notifier) => notifiers.includes(notifier.name));
  const notifierLabel = activeNotifiers.length > 0
    ? activeNotifiers.map((n) => `${n.type}:${n.name}`).join(", ")
    : "none";
  const customDaysLabel = customDays.length > 0 ? customDays.join(",") : "(none)";
  const daysLabel = daysOption === "custom" ? customDaysLabel : daysOption;
  const timePreview = triggerType === "time"
    ? scheduleMode === "schedule"
      ? `${daysLabel} @ ${timeValue || "--:--"}`
      : `Every ${intervalValue || "--"} ${daysLabel}${(startValue || endValue) ? `, ${startValue || "--:--"}-${endValue || "--:--"}` : ""}`
    : eventType;
  const modelPreview = selectedModel ? ` model=${selectedModel}` : "";
  const preview = triggerType === "time"
    ? `${timePreview} (${timezone}) -> ${notifierLabel}${modelPreview}`
    : `on ${eventType}${eventType === "event_approaching" ? ` (${eventLeadValue || "60m"})` : ""} -> ${notifierLabel}${modelPreview}`;
  const scheduleError = triggerType === "time" && daysOption === "custom" && customDays.length === 0
    ? "Select at least one day"
    : null;
  const statusText = `Writable: ${writable ? "yes" : "no"}   Save: ${canSave ? "enabled" : "disabled"}   Conflicts: none`;
  const nameInputWidth = Math.max(8, width - LABEL_WIDTH);

  return (
    <box flexDirection="column" width={width}>
      <box flexDirection="row">
        {labelCell("NAME", focus === "name")}
        <TextInputField
          value={nameValue}
          cursorPos={nameCursorPos}
          placeholder="My morning digest"
          showCursor={focus === "name"}
        />
      </box>

      <box flexDirection="row">
        {labelCell("DESCRIPTION", focus === "description")}
        <box flexGrow={1}>
          <TextEditArea
            value={descValue}
            cursorPos={descCursorPos}
            onValueChange={() => {}}
            onCursorChange={() => {}}
            placeholder="Send a summary + inbox triage suggestions"
            showCursor={focus === "description"}
          />
        </box>
      </box>

      <box flexDirection="row">
        {labelCell("MODEL", focus === "model")}
        <text>
          <span fg={focus === "model" ? colors.text.primary : colors.text.secondary}>
            {selectedModel || "default"}
          </span>
          <span fg={colors.text.muted}> (enter to choose)</span>
        </text>
      </box>

      <box marginTop={1} />

      {selectorRow("TRIGGER", focus === "trigger_type", TRIGGER_TYPES, triggerType)}

      {triggerType === "time" && (
        <>
          {selectorRow("MODE", focus === "mode", SCHEDULE_MODES, scheduleMode)}

          {scheduleMode === "schedule" ? (
            <box flexDirection="row">
              {labelCell("TIME", focus === "time")}
              <TextInputField
                value={timeValue}
                cursorPos={timeCursorPos}
                placeholder="09:00"
                showCursor={focus === "time"}
              />
            </box>
          ) : (
            <>
              <box flexDirection="row">
                {labelCell("EVERY", focus === "interval")}
                <TextInputField
                  value={intervalValue}
                  cursorPos={intervalCursorPos}
                  placeholder="30m"
                  showCursor={focus === "interval"}
                />
              </box>
              <box flexDirection="row">
                {labelCell("WINDOW", focus === "start" || focus === "end")}
                <TextInputField
                  value={startValue}
                  cursorPos={startCursorPos}
                  placeholder="08:00"
                  showCursor={focus === "start"}
                />
                <text><span fg={colors.text.muted}> </span></text>
                <text><span fg={colors.text.muted}>{renderWindowBar(startValue, endValue)}</span></text>
                <text><span fg={colors.text.muted}> </span></text>
                <TextInputField
                  value={endValue}
                  cursorPos={endCursorPos}
                  placeholder="18:00"
                  showCursor={focus === "end"}
                />
              </box>
            </>
          )}

          {selectorRow("DAYS", focus === "days", daysOptions, daysOption)}

          {daysOption === "custom" && (
            <>
              <box flexDirection="row">
                {labelCell("PICK", focus === "day_picker")}
                <box flexDirection="row" flexWrap="wrap">
                  {DAY_NAMES.map((day, idx) => {
                    const isSelected = customDays.includes(day);
                    const isCursor = focus === "day_picker" && idx === dayCursor;
                    return dayCell(day, isSelected, isCursor);
                  })}
                </box>
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
          )}
        </>
      )}

      {triggerType === "event" && (
        <>
          {selectorRow("EVENT", focus === "event_type", EVENT_TYPES, eventType)}
          {eventType === "event_approaching" && (
            <box flexDirection="row">
              {labelCell("LEAD", focus === "event_lead")}
              <TextInputField
                value={eventLeadValue}
                cursorPos={eventLeadCursorPos}
                placeholder="60m"
                showCursor={focus === "event_lead"}
              />
            </box>
          )}
        </>
      )}

      <box marginTop={1} />

      {availableNotifiers.length > 0 && (
        <>
          <box flexDirection="row">
            {labelCell("NOTIFIERS", focus === "notifiers")}
            <text><span fg={colors.text.muted}>select targets</span></text>
          </box>
          <box flexDirection="column">
            {availableNotifiers.map((notifier, idx) => {
              const isCursor = focus === "notifiers" && idx === notifierCursor;
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
      )}

      <box flexDirection="row">
        {labelCell("WRITABLE", focus === "writable")}
        <text><span fg={focus === "writable" ? colors.text.primary : colors.text.secondary}>{writable ? "yes" : "no"}</span></text>
      </box>

      <box marginTop={1}>
        <box flexDirection="row">
          {labelCell("PREVIEW", false)}
          <text><span fg={colors.text.secondary}>{preview}</span></text>
        </box>
      </box>

      <box>
        <box flexDirection="row">
          {labelCell("STATUS", false)}
          <text><span fg={colors.text.secondary}>{statusText}</span></text>
        </box>
      </box>

      {(scheduleError || error) && (
        <box marginTop={1}>
          <box flexDirection="row">
            {labelCell("ERROR", false)}
            <text><span fg={colors.status.error}>{scheduleError ?? error}</span></text>
          </box>
        </box>
      )}

      {saving && (
        <box marginTop={1}>
          <box flexDirection="row">
            {labelCell("SAVING", false)}
            <text><span fg={colors.tool.running}>Creating automation...</span></text>
          </box>
        </box>
      )}

      {!saving && !nameValue.trim() && !descValue.trim() && (
        <box marginTop={1}>
          <box flexDirection="row">
            {labelCell("HELP", false)}
            <text><span fg={colors.text.muted}>tab next  arrows move/select  space toggle  ctrl+s save</span></text>
          </box>
        </box>
      )}
    </box>
  );
}
