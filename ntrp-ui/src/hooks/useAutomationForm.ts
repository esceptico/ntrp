import { useState, useCallback } from "react";
import type { Automation, CreateAutomationData, UpdateAutomationData } from "../api/client.js";
import { useInlineTextInput } from "./useInlineTextInput.js";
import { useTextInput } from "./useTextInput.js";
import { useAutomationTriggerState } from "./useAutomationTriggerState.js";
import { useAutomationModelPicker } from "./useAutomationModelPicker.js";
import {
  SCHEDULE_DAYS,
  INTERVAL_DAYS,
  type CreateFocus,
} from "../components/viewers/automations/AutomationCreateView.js";

export function buildAutomationPayload(params: {
  name: string;
  description: string;
  model: string;
  triggerType: "time" | "event";
  scheduleMode: "schedule" | "interval";
  time: string;
  every: string;
  start: string;
  end: string;
  daysOption: string;
  customDays: string[];
  eventType: string;
  eventLead: number;
  notifiers: string[];
  writable: boolean;
}): CreateAutomationData | UpdateAutomationData {
  const data: CreateAutomationData | UpdateAutomationData = {
    name: params.name,
    description: params.description,
    model: params.model,
    trigger_type: params.triggerType,
    notifiers: params.notifiers,
    writable: params.writable,
  };

  if (params.triggerType === "time") {
    if (params.scheduleMode === "schedule") {
      data.at = params.time;
    } else {
      data.every = params.every;
      if (params.start && params.end) {
        data.start = params.start;
        data.end = params.end;
      }
    }
    if (params.daysOption === "custom") {
      data.days = params.customDays.join(",");
    } else if (params.daysOption !== "once" && params.daysOption !== "always") {
      data.days = params.daysOption;
    }
  } else {
    data.event_type = params.eventType;
    if (params.eventType === "event_approaching") {
      data.lead_minutes = params.eventLead;
    }
  }

  return data;
}

export function createFocusOrder(params: {
  triggerType: "time" | "event";
  scheduleMode: "schedule" | "interval";
  daysOption: string;
  eventType: string;
  hasNotifiers: boolean;
}): CreateFocus[] {
  const order: CreateFocus[] = ["name", "description", "model", "trigger_type"];
  if (params.triggerType === "time") {
    order.push("mode");
    if (params.scheduleMode === "schedule") {
      order.push("time");
    } else {
      order.push("interval", "start", "end");
    }
    order.push("days");
    if (params.daysOption === "custom") order.push("day_picker");
  } else {
    order.push("event_type");
    if (params.eventType === "event_approaching") order.push("event_lead");
  }
  if (params.hasNotifiers) order.push("notifiers");
  order.push("writable");
  return order;
}

interface UseAutomationFormParams {
  availableModels: string[];
  setCreateMode: React.Dispatch<React.SetStateAction<boolean>>;
  setCreateError: React.Dispatch<React.SetStateAction<string | null>>;
}

export interface AutomationFormState {
  editingTaskId: string | null;
  createFocus: CreateFocus;
  createEditing: boolean;
  createTriggerType: "time" | "event";
  createScheduleMode: "schedule" | "interval";
  createDaysOption: string;
  createEventType: string;
  createWritable: boolean;
  createNotifiers: string[];
  createNotifierCursor: number;
  createCustomDays: string[];
  createDayCursor: number;
  createModelCustomOption: string | null;
  createModelIndex: number;
  showModelDropdown: boolean;
  createDesc: string;
  createDescCursor: number;
  nameInput: ReturnType<typeof useInlineTextInput>;
  descInput: ReturnType<typeof useTextInput>;
  timeInput: ReturnType<typeof useInlineTextInput>;
  intervalInput: ReturnType<typeof useInlineTextInput>;
  startInput: ReturnType<typeof useInlineTextInput>;
  endInput: ReturnType<typeof useInlineTextInput>;
  eventLeadInput: ReturnType<typeof useInlineTextInput>;
  createModelOptions: string[];
  selectedModel: string;
  setEditingTaskId: React.Dispatch<React.SetStateAction<string | null>>;
  setCreateFocus: React.Dispatch<React.SetStateAction<CreateFocus>>;
  setCreateEditing: React.Dispatch<React.SetStateAction<boolean>>;
  setCreateTriggerType: React.Dispatch<React.SetStateAction<"time" | "event">>;
  setCreateScheduleMode: React.Dispatch<React.SetStateAction<"schedule" | "interval">>;
  setCreateDaysOption: React.Dispatch<React.SetStateAction<string>>;
  setCreateEventType: React.Dispatch<React.SetStateAction<string>>;
  setCreateWritable: React.Dispatch<React.SetStateAction<boolean>>;
  setCreateNotifiers: React.Dispatch<React.SetStateAction<string[]>>;
  setCreateNotifierCursor: React.Dispatch<React.SetStateAction<number>>;
  setCreateCustomDays: React.Dispatch<React.SetStateAction<string[]>>;
  setCreateDayCursor: React.Dispatch<React.SetStateAction<number>>;
  setCreateModelCustomOption: React.Dispatch<React.SetStateAction<string | null>>;
  setCreateModelIndex: React.Dispatch<React.SetStateAction<number>>;
  setShowModelDropdown: React.Dispatch<React.SetStateAction<boolean>>;
  setCreateDesc: React.Dispatch<React.SetStateAction<string>>;
  setCreateDescCursor: React.Dispatch<React.SetStateAction<number>>;
  resetCreateState: () => void;
  getCreateValidationError: () => string | null;
  openFullEditor: (item: Automation) => void;
  parseLeadToMinutes: (raw: string) => number | null;
}

export function useAutomationForm({
  availableModels,
  setCreateMode,
  setCreateError,
}: UseAutomationFormParams): AutomationFormState {
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null);
  const [createFocus, setCreateFocus] = useState<CreateFocus>("name");
  const [createEditing, setCreateEditing] = useState(false);
  const [createWritable, setCreateWritable] = useState(false);
  const [createNotifiers, setCreateNotifiers] = useState<string[]>([]);
  const [createNotifierCursor, setCreateNotifierCursor] = useState(0);

  const nameInput = useInlineTextInput();
  const [createDesc, setCreateDesc] = useState("");
  const [createDescCursor, setCreateDescCursor] = useState(0);
  const descInput = useTextInput({
    text: createDesc,
    cursorPos: createDescCursor,
    setText: setCreateDesc,
    setCursorPos: setCreateDescCursor,
  });

  const trigger = useAutomationTriggerState();
  const model = useAutomationModelPicker(availableModels);

  const resetCreateState = useCallback(() => {
    setEditingTaskId(null);
    setCreateMode(false);
    setCreateFocus("name");
    setCreateEditing(false);
    setCreateWritable(false);
    setCreateNotifiers([]);
    setCreateNotifierCursor(0);
    setCreateError(null);
    nameInput.reset();
    setCreateDesc("");
    setCreateDescCursor(0);
    trigger.resetTriggerState();
    model.resetModelState();
  }, [
    setCreateMode,
    setCreateError,
    nameInput,
    trigger,
    model,
  ]);

  const getCreateValidationError = useCallback((): string | null => {
    const name = nameInput.value.trim();
    const description = createDesc.trim();
    if (!name || !description) return "Name and description are required";
    if (trigger.createTriggerType === "time") {
      if (trigger.createScheduleMode === "schedule") {
        const at = trigger.timeInput.value.trim();
        if (!at) return "Time is required for schedule mode";
      } else {
        const every = trigger.intervalInput.value.trim();
        if (!every) return "Interval is required for interval mode";
        const start = trigger.startInput.value.trim();
        const end = trigger.endInput.value.trim();
        if ((start && !end) || (!start && end)) return "Both start and end times are required";
      }
      if (trigger.createDaysOption === "custom" && trigger.createCustomDays.length === 0) {
        return "Select at least one day";
      }
    }
    if (trigger.createTriggerType === "event" && trigger.createEventType === "event_approaching") {
      const lead = trigger.parseLeadToMinutes(trigger.eventLeadInput.value);
      if (lead === null) return "Lead time must be like 30m or 2h30m";
    }
    return null;
  }, [
    nameInput.value,
    createDesc,
    trigger.createTriggerType,
    trigger.createScheduleMode,
    trigger.createDaysOption,
    trigger.createCustomDays,
    trigger.createEventType,
    trigger.timeInput.value,
    trigger.intervalInput.value,
    trigger.startInput.value,
    trigger.endInput.value,
    trigger.eventLeadInput.value,
    trigger.parseLeadToMinutes,
  ]);

  const openFullEditor = useCallback((item: Automation) => {
    setEditingTaskId(item.task_id);
    setCreateMode(true);
    setCreateError(null);
    setCreateFocus("name");

    nameInput.reset();
    nameInput.setValue(item.name ?? "");
    const itemModel = item.model ?? "";
    if (itemModel && !model.createModelOptions.includes(itemModel)) {
      model.setCreateModelCustomOption(itemModel);
      model.setCreateModelIndex(model.createModelOptions.length);
    } else {
      model.setCreateModelCustomOption(null);
      const DEFAULT_MODEL_OPTION = "__default__";
      const idx = model.createModelOptions.indexOf(itemModel || DEFAULT_MODEL_OPTION);
      model.setCreateModelIndex(idx >= 0 ? idx : 0);
    }
    setCreateDesc(item.description ?? "");
    setCreateDescCursor((item.description ?? "").length);

    setCreateNotifiers(item.notifiers ?? []);
    setCreateNotifierCursor(0);
    setCreateWritable(item.writable);
    trigger.setCreateCustomDays([]);
    trigger.setCreateDayCursor(0);

    if (item.trigger.type === "event") {
      trigger.setCreateTriggerType("event");
      trigger.setCreateEventType(item.trigger.event_type);
      trigger.eventLeadInput.reset();
      trigger.eventLeadInput.setValue(`${item.trigger.lead_minutes ?? 60}m`);
      trigger.setCreateScheduleMode("schedule");
      trigger.setCreateDaysOption("once");
      trigger.timeInput.reset();
      trigger.intervalInput.reset();
      trigger.startInput.reset();
      trigger.endInput.reset();
      return;
    }

    trigger.setCreateTriggerType("time");
    if (item.trigger.every) {
      trigger.setCreateScheduleMode("interval");
      trigger.intervalInput.reset();
      trigger.intervalInput.setValue(item.trigger.every);
      trigger.startInput.reset();
      trigger.endInput.reset();
      if (item.trigger.start) trigger.startInput.setValue(item.trigger.start);
      if (item.trigger.end) trigger.endInput.setValue(item.trigger.end);
      trigger.timeInput.reset();
    } else {
      trigger.setCreateScheduleMode("schedule");
      trigger.timeInput.reset();
      if (item.trigger.at) trigger.timeInput.setValue(item.trigger.at);
      trigger.intervalInput.reset();
      trigger.startInput.reset();
      trigger.endInput.reset();
    }

    const rawDays = item.trigger.days;
    const scheduleDefault = item.trigger.every ? "always" : "once";
    const allowed = item.trigger.every ? INTERVAL_DAYS : SCHEDULE_DAYS;
    if (!rawDays) {
      trigger.setCreateDaysOption(scheduleDefault);
    } else if ((allowed as readonly string[]).includes(rawDays)) {
      trigger.setCreateDaysOption(rawDays);
    } else {
      trigger.setCreateDaysOption("custom");
      trigger.setCreateCustomDays(rawDays.split(",").map((d) => d.trim()).filter(Boolean));
    }
  }, [
    setCreateMode,
    setCreateError,
    setCreateFocus,
    setCreateNotifiers,
    setCreateNotifierCursor,
    setCreateWritable,
    nameInput,
    model,
    setCreateDesc,
    setCreateDescCursor,
    trigger,
  ]);

  return {
    editingTaskId,
    createFocus,
    createEditing,
    createTriggerType: trigger.createTriggerType,
    createScheduleMode: trigger.createScheduleMode,
    createDaysOption: trigger.createDaysOption,
    createEventType: trigger.createEventType,
    createWritable,
    createNotifiers,
    createNotifierCursor,
    createCustomDays: trigger.createCustomDays,
    createDayCursor: trigger.createDayCursor,
    createModelCustomOption: model.createModelCustomOption,
    createModelIndex: model.createModelIndex,
    showModelDropdown: model.showModelDropdown,
    createDesc,
    createDescCursor,
    nameInput,
    descInput,
    timeInput: trigger.timeInput,
    intervalInput: trigger.intervalInput,
    startInput: trigger.startInput,
    endInput: trigger.endInput,
    eventLeadInput: trigger.eventLeadInput,
    createModelOptions: model.createModelOptions,
    selectedModel: model.selectedModel,
    setEditingTaskId,
    setCreateFocus,
    setCreateEditing,
    setCreateTriggerType: trigger.setCreateTriggerType,
    setCreateScheduleMode: trigger.setCreateScheduleMode,
    setCreateDaysOption: trigger.setCreateDaysOption,
    setCreateEventType: trigger.setCreateEventType,
    setCreateWritable,
    setCreateNotifiers,
    setCreateNotifierCursor,
    setCreateCustomDays: trigger.setCreateCustomDays,
    setCreateDayCursor: trigger.setCreateDayCursor,
    setCreateModelCustomOption: model.setCreateModelCustomOption,
    setCreateModelIndex: model.setCreateModelIndex,
    setShowModelDropdown: model.setShowModelDropdown,
    setCreateDesc,
    setCreateDescCursor,
    resetCreateState,
    getCreateValidationError,
    openFullEditor,
    parseLeadToMinutes: trigger.parseLeadToMinutes,
  };
}
