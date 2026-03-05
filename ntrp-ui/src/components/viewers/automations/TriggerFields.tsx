import { colors, TextInputField } from "../../ui/index.js";
import {
  SCHEDULE_MODES, SCHEDULE_DAYS, INTERVAL_DAYS, EVENT_TYPES,
  type CreateFocus,
} from "./AutomationCreateView.js";
import { labelCell, selectorRow } from "./FormHelpers.js";
import { DayPicker } from "./DayPicker.js";

export interface TriggerFieldsProps {
  focus: CreateFocus;
  editing: boolean;
  triggerType: "time" | "event";
  scheduleMode: "schedule" | "interval";
  daysOption: string;
  eventType: string;
  customDays: string[];
  dayCursor: number;
  timeValue: string;
  timeCursorPos: number;
  intervalValue: string;
  intervalCursorPos: number;
  startValue: string;
  startCursorPos: number;
  endValue: string;
  endCursorPos: number;
  eventLeadValue: string;
  eventLeadCursorPos: number;
}

function parseHmToMinutes(value: string): number | null {
  const m = /^(\d{1,2}):(\d{2})$/.exec(value.trim());
  if (!m) return null;
  const hours = Number(m[1]);
  const mins = Number(m[2]);
  if (hours < 0 || hours > 23 || mins < 0 || mins > 59) return null;
  return (hours * 60) + mins;
}

function renderWindowBar(start: string, end: string): string {
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
    bar += i >= startIdx && i < endIdx ? "\u2588" : "-";
  }
  bar += "|";
  return bar;
}

export function TriggerFields({
  focus, editing, triggerType, scheduleMode, daysOption, eventType,
  customDays, dayCursor,
  timeValue, timeCursorPos,
  intervalValue, intervalCursorPos,
  startValue, startCursorPos,
  endValue, endCursorPos,
  eventLeadValue, eventLeadCursorPos,
}: TriggerFieldsProps) {
  const daysOptions = scheduleMode === "schedule" ? SCHEDULE_DAYS : INTERVAL_DAYS;

  return (
    <>
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
                showCursor={editing && focus === "time"}
              />
              {focus === "time" && !editing && <text><span fg={colors.text.muted}> enter to edit</span></text>}
            </box>
          ) : (
            <>
              <box flexDirection="row">
                {labelCell("EVERY", focus === "interval")}
                <TextInputField
                  value={intervalValue}
                  cursorPos={intervalCursorPos}
                  placeholder="30m"
                  showCursor={editing && focus === "interval"}
                />
                {focus === "interval" && !editing && <text><span fg={colors.text.muted}> enter to edit</span></text>}
              </box>
              <box flexDirection="row">
                {labelCell("WINDOW", focus === "start" || focus === "end")}
                <TextInputField
                  value={startValue}
                  cursorPos={startCursorPos}
                  placeholder="08:00"
                  showCursor={editing && focus === "start"}
                />
                <text><span fg={colors.text.muted}> </span></text>
                <text><span fg={colors.text.muted}>{renderWindowBar(startValue, endValue)}</span></text>
                <text><span fg={colors.text.muted}> </span></text>
                <TextInputField
                  value={endValue}
                  cursorPos={endCursorPos}
                  placeholder="18:00"
                  showCursor={editing && focus === "end"}
                />
                {(focus === "start" || focus === "end") && !editing && <text><span fg={colors.text.muted}> enter to edit</span></text>}
              </box>
            </>
          )}

          {selectorRow("DAYS", focus === "days", daysOptions, daysOption)}

          {daysOption === "custom" && (
            <DayPicker
              focus={focus}
              editing={editing}
              customDays={customDays}
              dayCursor={dayCursor}
            />
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
                showCursor={editing && focus === "event_lead"}
              />
              {focus === "event_lead" && !editing && <text><span fg={colors.text.muted}> enter to edit</span></text>}
            </box>
          )}
        </>
      )}
    </>
  );
}
