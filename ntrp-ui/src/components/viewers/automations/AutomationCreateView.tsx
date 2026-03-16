import { colors, TextInputField, TextEditArea } from "../../ui/index.js";
import type { NotifierSummary, Trigger } from "../../../api/client.js";
import type { TriggerType } from "../../../hooks/useAutomationTriggerState.js";
import { triggerLabel } from "../../../lib/format.js";
import { labelCell, selectorRow } from "./FormHelpers.js";
import { TriggerFields } from "./TriggerFields.js";
import { NotifierSelector } from "./NotifierSelector.js";

export type CreateFocus = "name" | "description" | "model" | "triggers_list" | "cooldown" | "trigger_type" | "mode" | "time" | "interval" | "start" | "end" | "days" | "day_picker" | "event_type" | "event_lead" | "idle_minutes" | "every_n" | "notifiers" | "writable";

export const TRIGGER_TYPES = ["time", "event", "idle", "count"] as const;
export const SCHEDULE_MODES = ["schedule", "interval"] as const;
export const SCHEDULE_DAYS = ["once", "daily", "weekdays", "custom"] as const;
export const INTERVAL_DAYS = ["always", "weekdays", "custom"] as const;
export const EVENT_TYPES = ["event_approaching"] as const;
export const DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;

interface AutomationCreateViewProps {
  focus: CreateFocus;
  editing: boolean;
  triggerType: TriggerType;
  scheduleMode: "schedule" | "interval";
  daysOption: string;
  eventType: string;
  writable: boolean;
  saving: boolean;
  error: string | null;
  triggerError: string | null;
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
  idleMinutesValue: string;
  idleMinutesCursorPos: number;
  everyNValue: string;
  everyNCursorPos: number;
  cooldownValue: string;
  cooldownCursorPos: number;
  canSave: boolean;
  triggersList: Trigger[];
  triggerCursor: number;
  editingTriggerIndex: number | null;
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
  triggerError,
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
  idleMinutesValue,
  idleMinutesCursorPos,
  everyNValue,
  everyNCursorPos,
  cooldownValue,
  cooldownCursorPos,
  canSave,
  triggersList,
  triggerCursor,
  editingTriggerIndex,
}: AutomationCreateViewProps) {
  const isEditingTrigger = editingTriggerIndex !== null;
  const isFocusOnTriggersList = focus === "triggers_list";

  return (
    <box flexDirection="column" width={width}>
      {/* --- Main fields (dimmed when editing trigger) --- */}
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
            placeholder="What the agent should do"
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

      {/* --- Triggers list --- */}
      <box flexDirection="column">
        {labelCell("TRIGGERS", isFocusOnTriggersList)}
        {triggersList.length === 0 ? (
          <text>
            <span fg={isFocusOnTriggersList ? colors.text.primary : colors.text.muted}>
              {"  (none)  "}
            </span>
            {isFocusOnTriggersList && <span fg={colors.text.muted}>a to add</span>}
          </text>
        ) : (
          triggersList.map((t, i) => {
            const isSelected = isFocusOnTriggersList && i === triggerCursor;
            const isBeingEdited = editingTriggerIndex === i;
            const indicator = isSelected ? "\u25B8 " : "  ";
            const editBadge = isBeingEdited ? " \u2190 editing" : "";
            const color = isSelected
              ? colors.text.primary
              : isBeingEdited
                ? colors.selection.active
                : colors.text.secondary;
            return (
              <text key={i}>
                <span fg={color}>{indicator}{triggerLabel(t)}{editBadge}</span>
              </text>
            );
          })
        )}
        {isFocusOnTriggersList && triggersList.length > 0 && (
          <text><span fg={colors.text.muted}>  enter=edit  a=add  d=remove</span></text>
        )}
      </box>

      {/* --- Trigger editor (only when editing a trigger) --- */}
      {isEditingTrigger && (
        <box flexDirection="column" marginTop={1} paddingLeft={2}>
          <text><span fg={colors.selection.active}>{"--- editing trigger ---"}</span></text>

          {selectorRow("TYPE", focus === "trigger_type", TRIGGER_TYPES, triggerType)}

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
            idleMinutesValue={idleMinutesValue}
            idleMinutesCursorPos={idleMinutesCursorPos}
            everyNValue={everyNValue}
            everyNCursorPos={everyNCursorPos}
          />

          {triggerError && (
            <text><span fg={colors.status.error}>{triggerError}</span></text>
          )}

          <text><span fg={colors.text.muted}>esc to save trigger and return</span></text>
        </box>
      )}

      <box marginTop={1} />

      {/* --- Cooldown --- */}
      <box flexDirection="row">
        {labelCell("COOLDOWN", focus === "cooldown")}
        <TextInputField
          value={cooldownValue}
          cursorPos={cooldownCursorPos}
          placeholder="0"
          showCursor={editing && focus === "cooldown"}
        />
        <text><span fg={colors.text.muted}> min between runs</span></text>
        {focus === "cooldown" && !editing && <text><span fg={colors.text.muted}>  enter to edit</span></text>}
      </box>

      {/* --- Notifiers & writable --- */}
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

      {/* --- Status --- */}
      <box marginTop={1}>
        <box flexDirection="row">
          {labelCell("STATUS", false)}
          <text><span fg={colors.text.secondary}>{`Save: ${canSave ? "ready" : "incomplete"}   Writable: ${writable ? "yes" : "no"}`}</span></text>
        </box>
      </box>

      {error && (
        <box marginTop={1}>
          <box flexDirection="row">
            {labelCell("ERROR", false)}
            <text><span fg={colors.status.error}>{error}</span></text>
          </box>
        </box>
      )}

      {saving && (
        <box marginTop={1}>
          <box flexDirection="row">
            {labelCell("SAVING", false)}
            <text><span fg={colors.tool.running}>Saving...</span></text>
          </box>
        </box>
      )}
    </box>
  );
}
