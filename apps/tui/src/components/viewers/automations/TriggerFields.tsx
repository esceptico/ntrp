import { colors, TextInputField } from "../../ui/index.js";
import type { TriggerType } from "../../../hooks/useAutomationTriggerState.js";
import {
  SCHEDULE_MODES, SCHEDULE_DAYS, INTERVAL_DAYS, EVENT_TYPES,
  type CreateFocus,
} from "./AutomationCreateView.js";
import { labelCell, selectorRow } from "./FormHelpers.js";
import { DayPicker } from "./DayPicker.js";

export interface TriggerFieldsProps {
  focus: CreateFocus;
  editing: boolean;
  triggerType: TriggerType;
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
  idleMinutesValue: string;
  idleMinutesCursorPos: number;
  everyNValue: string;
  everyNCursorPos: number;
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
  idleMinutesValue, idleMinutesCursorPos,
  everyNValue, everyNCursorPos,
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
                {labelCell("ACTIVE", focus === "start" || focus === "end")}
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
                {(focus === "start" || focus === "end") && !editing && <text><span fg={colors.text.muted}> optional active window</span></text>}
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

      {triggerType === "idle" && (
        <box flexDirection="row">
          {labelCell("AFTER", focus === "idle_minutes")}
          <TextInputField
            value={idleMinutesValue}
            cursorPos={idleMinutesCursorPos}
            placeholder="5"
            showCursor={editing && focus === "idle_minutes"}
          />
          <text><span fg={colors.text.muted}> minutes of inactivity</span></text>
          {focus === "idle_minutes" && !editing && <text><span fg={colors.text.muted}>  enter to edit</span></text>}
        </box>
      )}

      {triggerType === "count" && (
        <box flexDirection="row">
          {labelCell("EVERY", focus === "every_n")}
          <TextInputField
            value={everyNValue}
            cursorPos={everyNCursorPos}
            placeholder="10"
            showCursor={editing && focus === "every_n"}
          />
          <text><span fg={colors.text.muted}> turns</span></text>
          {focus === "every_n" && !editing && <text><span fg={colors.text.muted}>  enter to edit</span></text>}
        </box>
      )}
    </>
  );
}
