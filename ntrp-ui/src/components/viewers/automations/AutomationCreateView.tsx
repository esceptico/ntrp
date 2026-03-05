import { colors, TextInputField, TextEditArea } from "../../ui/index.js";
import type { NotifierSummary } from "../../../api/client.js";
import { labelCell, selectorRow } from "./FormHelpers.js";
import { TriggerFields } from "./TriggerFields.js";
import { NotifierSelector } from "./NotifierSelector.js";

export type CreateFocus = "name" | "description" | "model" | "trigger_type" | "mode" | "time" | "interval" | "start" | "end" | "days" | "day_picker" | "event_type" | "event_lead" | "notifiers" | "writable";

export const TRIGGER_TYPES = ["time", "event"] as const;
export const SCHEDULE_MODES = ["schedule", "interval"] as const;
export const SCHEDULE_DAYS = ["once", "daily", "weekdays", "custom"] as const;
export const INTERVAL_DAYS = ["always", "weekdays", "custom"] as const;
export const EVENT_TYPES = ["event_approaching"] as const;
export const DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;

interface AutomationCreateViewProps {
  focus: CreateFocus;
  editing: boolean;
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
  editing,
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
  const activeNotifiers = availableNotifiers.filter((notifier) => notifiers.includes(notifier.name));
  const notifierLabel = activeNotifiers.length > 0
    ? activeNotifiers.map((n) => `${n.type}:${n.name}`).join(", ")
    : "none";
  const customDaysLabel = customDays.length > 0 ? customDays.join(",") : "(none)";
  const daysLabel = daysOption === "custom" ? customDaysLabel : daysOption;
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
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

  return (
    <box flexDirection="column" width={width}>
      <box flexDirection="row">
        {labelCell("NAME", focus === "name")}
        <TextInputField
          value={nameValue}
          cursorPos={nameCursorPos}
          placeholder="My morning digest"
          showCursor={editing && focus === "name"}
        />
        {focus === "name" && !editing && <text><span fg={colors.text.muted}> enter to edit</span></text>}
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
            showCursor={editing && focus === "description"}
          />
        </box>
        {focus === "description" && !editing && <text><span fg={colors.text.muted}> enter to edit</span></text>}
      </box>

      <box flexDirection="row">
        {labelCell("MODEL", focus === "model")}
        <text>
          <span fg={focus === "model" ? colors.text.primary : colors.text.secondary}>
            {selectedModel || "default"}
          </span>
          {focus === "model" && <span fg={colors.text.muted}> enter to choose</span>}
        </text>
      </box>

      <box marginTop={1} />

      {selectorRow("TRIGGER", focus === "trigger_type", TRIGGER_TYPES, triggerType)}

      <TriggerFields
        focus={focus}
        editing={editing}
        triggerType={triggerType}
        scheduleMode={scheduleMode}
        daysOption={daysOption}
        eventType={eventType}
        customDays={customDays}
        dayCursor={dayCursor}
        timeValue={timeValue}
        timeCursorPos={timeCursorPos}
        intervalValue={intervalValue}
        intervalCursorPos={intervalCursorPos}
        startValue={startValue}
        startCursorPos={startCursorPos}
        endValue={endValue}
        endCursorPos={endCursorPos}
        eventLeadValue={eventLeadValue}
        eventLeadCursorPos={eventLeadCursorPos}
      />

      <box marginTop={1} />

      {availableNotifiers.length > 0 && (
        <NotifierSelector
          focus={focus}
          editing={editing}
          availableNotifiers={availableNotifiers}
          notifiers={notifiers}
          notifierCursor={notifierCursor}
        />
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

    </box>
  );
}
