import { useState, useCallback } from "react";
import type { Automation, CreateAutomationData, Trigger, UpdateAutomationData } from "../api/client.js";
import { useInlineTextInput } from "./useInlineTextInput.js";
import { useTextInput } from "./useTextInput.js";
import { useAutomationTriggerState, type TriggerType } from "./useAutomationTriggerState.js";
import { useAutomationModelPicker } from "./useAutomationModelPicker.js";
import {
  SCHEDULE_DAYS,
  INTERVAL_DAYS,
  type CreateFocus,
} from "../components/viewers/automations/AutomationCreateView.js";

// --- Build a Trigger object from the form fields ---

function buildTriggerFromFields(params: {
  triggerType: TriggerType;
  scheduleMode: "schedule" | "interval";
  time: string;
  every: string;
  start: string;
  end: string;
  daysOption: string;
  customDays: string[];
  eventType: string;
  eventLead: number;
  idleMinutes: number;
  everyN: number;
}): Trigger {
  if (params.triggerType === "idle") {
    return { type: "idle", idle_minutes: params.idleMinutes };
  }
  if (params.triggerType === "count") {
    return { type: "count", every_n: params.everyN };
  }
  if (params.triggerType === "event") {
    const t: Trigger = { type: "event", event_type: params.eventType };
    if (params.eventType === "event_approaching") {
      t.lead_minutes = params.eventLead;
    }
    return t;
  }
  const t: Trigger = { type: "time" };
  if (params.scheduleMode === "schedule") {
    t.at = params.time;
  } else {
    t.every = params.every;
    if (params.start && params.end) {
      t.start = params.start;
      t.end = params.end;
    }
  }
  if (params.daysOption === "custom") {
    t.days = params.customDays.join(",");
  } else if (params.daysOption !== "once" && params.daysOption !== "always") {
    t.days = params.daysOption;
  }
  return t;
}

export { buildTriggerFromFields };

// --- Build the API payload ---

export function buildAutomationPayload(params: {
  name: string;
  description: string;
  model: string;
  writable: boolean;
  triggers: Trigger[];
  cooldown_minutes: number | undefined;
}): CreateAutomationData {
  return {
    name: params.name,
    description: params.description,
    model: params.model,
    writable: params.writable,
    triggers: params.triggers,
    cooldown_minutes: params.cooldown_minutes,
  };
}

// --- Focus order ---

export function createFocusOrder(params: {
  editingTrigger: boolean;
  triggerType: TriggerType;
  scheduleMode: "schedule" | "interval";
  daysOption: string;
  eventType: string;
}): CreateFocus[] {
  if (!params.editingTrigger) {
    // Main form: triggers_list is a single focusable item
    const order: CreateFocus[] = ["name", "description", "model", "triggers_list", "cooldown"];
    order.push("writable");
    return order;
  }

  // Trigger editor fields
  const order: CreateFocus[] = ["trigger_type"];
  if (params.triggerType === "time") {
    order.push("mode");
    if (params.scheduleMode === "schedule") {
      order.push("time");
    } else {
      order.push("interval", "start", "end");
    }
    order.push("days");
    if (params.daysOption === "custom") order.push("day_picker");
  } else if (params.triggerType === "event") {
    order.push("event_type");
    if (params.eventType === "event_approaching") order.push("event_lead");
  } else if (params.triggerType === "idle") {
    order.push("idle_minutes");
  } else if (params.triggerType === "count") {
    order.push("every_n");
  }
  return order;
}

// --- Form state interface ---

interface UseAutomationFormParams {
  availableModels: string[];
  setCreateMode: React.Dispatch<React.SetStateAction<boolean>>;
  setCreateError: React.Dispatch<React.SetStateAction<string | null>>;
}

export interface AutomationFormState {
  editingTaskId: string | null;
  createFocus: CreateFocus;
  createEditing: boolean;
  createTriggerType: TriggerType;
  createScheduleMode: "schedule" | "interval";
  createDaysOption: string;
  createEventType: string;
  createWritable: boolean;
  createCustomDays: string[];
  createDayCursor: number;
  triggersList: Trigger[];
  triggerCursor: number;
  editingTriggerIndex: number | null;
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
  idleMinutesInput: ReturnType<typeof useInlineTextInput>;
  everyNInput: ReturnType<typeof useInlineTextInput>;
  cooldownInput: ReturnType<typeof useInlineTextInput>;
  createModelOptions: string[];
  selectedModel: string;
  setEditingTaskId: React.Dispatch<React.SetStateAction<string | null>>;
  setCreateFocus: React.Dispatch<React.SetStateAction<CreateFocus>>;
  setCreateEditing: React.Dispatch<React.SetStateAction<boolean>>;
  setCreateTriggerType: React.Dispatch<React.SetStateAction<TriggerType>>;
  setCreateScheduleMode: React.Dispatch<React.SetStateAction<"schedule" | "interval">>;
  setCreateDaysOption: React.Dispatch<React.SetStateAction<string>>;
  setCreateEventType: React.Dispatch<React.SetStateAction<string>>;
  setCreateWritable: React.Dispatch<React.SetStateAction<boolean>>;
  setCreateCustomDays: React.Dispatch<React.SetStateAction<string[]>>;
  setCreateDayCursor: React.Dispatch<React.SetStateAction<number>>;
  setTriggersList: React.Dispatch<React.SetStateAction<Trigger[]>>;
  setTriggerCursor: React.Dispatch<React.SetStateAction<number>>;
  setEditingTriggerIndex: React.Dispatch<React.SetStateAction<number | null>>;
  setCreateModelCustomOption: React.Dispatch<React.SetStateAction<string | null>>;
  setCreateModelIndex: React.Dispatch<React.SetStateAction<number>>;
  setShowModelDropdown: React.Dispatch<React.SetStateAction<boolean>>;
  setCreateDesc: React.Dispatch<React.SetStateAction<string>>;
  setCreateDescCursor: React.Dispatch<React.SetStateAction<number>>;
  // Actions
  enterTriggerEditor: (index: number) => void;
  addTrigger: () => void;
  removeTrigger: () => void;
  saveTriggerEdit: () => void;
  resetCreateState: () => void;
  getCreateValidationError: () => string | null;
  getTriggerValidationError: () => string | null;
  openFullEditor: (item: Automation) => void;
  parseLeadToMinutes: (raw: string) => number | null;
}

// --- Hook implementation ---

export function useAutomationForm({
  availableModels,
  setCreateMode,
  setCreateError,
}: UseAutomationFormParams): AutomationFormState {
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null);
  const [createFocus, setCreateFocus] = useState<CreateFocus>("name");
  const [createEditing, setCreateEditing] = useState(false);
  const [createWritable, setCreateWritable] = useState(false);

  const [triggersList, setTriggersList] = useState<Trigger[]>([]);
  const [triggerCursor, setTriggerCursor] = useState(0);
  const [editingTriggerIndex, setEditingTriggerIndex] = useState<number | null>(null);

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

  // Load a trigger into the editor fields
  const loadTriggerIntoFields = useCallback((t: Trigger) => {
    trigger.resetTriggerState();
    if (t.type === "idle") {
      trigger.setCreateTriggerType("idle");
      trigger.idleMinutesInput.reset();
      trigger.idleMinutesInput.setValue(String(t.idle_minutes));
    } else if (t.type === "count") {
      trigger.setCreateTriggerType("count");
      trigger.everyNInput.reset();
      trigger.everyNInput.setValue(String(t.every_n));
    } else if (t.type === "event") {
      trigger.setCreateTriggerType("event");
      trigger.setCreateEventType(t.event_type);
      trigger.eventLeadInput.reset();
      trigger.eventLeadInput.setValue(`${t.lead_minutes ?? 60}m`);
    } else {
      trigger.setCreateTriggerType("time");
      if (t.every) {
        trigger.setCreateScheduleMode("interval");
        trigger.intervalInput.reset();
        trigger.intervalInput.setValue(t.every);
        trigger.startInput.reset();
        trigger.endInput.reset();
        if (t.start) trigger.startInput.setValue(t.start);
        if (t.end) trigger.endInput.setValue(t.end);
        trigger.timeInput.reset();
      } else {
        trigger.setCreateScheduleMode("schedule");
        trigger.timeInput.reset();
        if (t.at) trigger.timeInput.setValue(t.at);
        trigger.intervalInput.reset();
        trigger.startInput.reset();
        trigger.endInput.reset();
      }
      const rawDays = t.days;
      const scheduleDefault = t.every ? "always" : "once";
      const allowed = t.every ? INTERVAL_DAYS : SCHEDULE_DAYS;
      if (!rawDays) {
        trigger.setCreateDaysOption(scheduleDefault);
      } else if ((allowed as readonly string[]).includes(rawDays)) {
        trigger.setCreateDaysOption(rawDays);
      } else {
        trigger.setCreateDaysOption("custom");
        trigger.setCreateCustomDays(rawDays.split(",").map((d) => d.trim()).filter(Boolean));
      }
    }
  }, [trigger]);

  // Build trigger from current field values
  const buildCurrentTrigger = useCallback((): Trigger => {
    return buildTriggerFromFields({
      triggerType: trigger.createTriggerType,
      scheduleMode: trigger.createScheduleMode,
      time: trigger.timeInput.value,
      every: trigger.intervalInput.value,
      start: trigger.startInput.value,
      end: trigger.endInput.value,
      daysOption: trigger.createDaysOption,
      customDays: trigger.createCustomDays,
      eventType: trigger.createEventType,
      eventLead: trigger.parseLeadToMinutes(trigger.eventLeadInput.value) ?? 60,
      idleMinutes: Number(trigger.idleMinutesInput.value) || 5,
      everyN: Number(trigger.everyNInput.value) || 10,
    });
  }, [trigger]);

  // Enter trigger editor for existing trigger
  const enterTriggerEditor = useCallback((index: number) => {
    const t = triggersList[index];
    if (!t) return;
    loadTriggerIntoFields(t);
    setEditingTriggerIndex(index);
    setCreateFocus("trigger_type");
    setCreateEditing(false);
  }, [triggersList, loadTriggerIntoFields]);

  // Add new trigger and enter editor
  const addTrigger = useCallback(() => {
    const newTrigger: Trigger = { type: "time", at: "09:00" };
    setTriggersList((prev) => [...prev, newTrigger]);
    const newIndex = triggersList.length;
    loadTriggerIntoFields(newTrigger);
    setEditingTriggerIndex(newIndex);
    setTriggerCursor(newIndex);
    setCreateFocus("trigger_type");
    setCreateEditing(false);
  }, [triggersList.length, loadTriggerIntoFields]);

  // Remove trigger at cursor
  const removeTrigger = useCallback(() => {
    if (triggersList.length === 0) return;
    setTriggersList((prev) => prev.filter((_, i) => i !== triggerCursor));
    setTriggerCursor((c) => Math.min(c, Math.max(0, triggersList.length - 2)));
  }, [triggersList.length, triggerCursor]);

  // Save current editor fields back to the list
  const saveTriggerEdit = useCallback(() => {
    if (editingTriggerIndex === null) return;
    const built = buildCurrentTrigger();
    setTriggersList((prev) => prev.map((t, i) => i === editingTriggerIndex ? built : t));
    setEditingTriggerIndex(null);
    setCreateFocus("triggers_list");
    setCreateEditing(false);
  }, [editingTriggerIndex, buildCurrentTrigger]);

  const resetCreateState = useCallback(() => {
    setEditingTaskId(null);
    setCreateMode(false);
    setCreateFocus("name");
    setCreateEditing(false);
    setCreateWritable(false);
    setCreateError(null);
    setTriggersList([]);
    setTriggerCursor(0);
    setEditingTriggerIndex(null);
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

  const getTriggerValidationError = useCallback((): string | null => {
    if (trigger.createTriggerType === "time") {
      if (trigger.createScheduleMode === "schedule") {
        if (!trigger.timeInput.value.trim()) return "Time is required (e.g. 09:00)";
      } else {
        if (!trigger.intervalInput.value.trim()) return "Frequency is required (e.g. 30m, 2h)";
        const start = trigger.startInput.value.trim();
        const end = trigger.endInput.value.trim();
        if ((start && !end) || (!start && end)) return "Both start and end required for active window";
      }
      if (trigger.createDaysOption === "custom" && trigger.createCustomDays.length === 0) {
        return "Select at least one day";
      }
    } else if (trigger.createTriggerType === "event") {
      if (trigger.createEventType === "event_approaching") {
        const lead = trigger.parseLeadToMinutes(trigger.eventLeadInput.value);
        if (lead === null) return "Lead time must be like 30m or 2h30m";
      }
    } else if (trigger.createTriggerType === "idle") {
      const mins = Number(trigger.idleMinutesInput.value);
      if (!mins || mins < 1) return "Idle minutes must be at least 1";
    } else if (trigger.createTriggerType === "count") {
      const n = Number(trigger.everyNInput.value);
      if (!n || n < 1) return "Turn count must be at least 1";
    }
    return null;
  }, [trigger]);

  const getCreateValidationError = useCallback((): string | null => {
    const name = nameInput.value.trim();
    const description = createDesc.trim();
    if (!name || !description) return "Name and description are required";
    if (triggersList.length === 0) return "At least one trigger is required";
    return null;
  }, [nameInput.value, createDesc, triggersList.length]);

  const openFullEditor = useCallback((item: Automation) => {
    setEditingTaskId(item.task_id);
    setCreateMode(true);
    setCreateError(null);
    setCreateFocus("name");
    setEditingTriggerIndex(null);

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
    setCreateWritable(item.writable);

    // Load all triggers into the list
    setTriggersList([...item.triggers]);
    setTriggerCursor(0);

    // Load cooldown
    trigger.cooldownInput.reset();
    if (item.cooldown_minutes) {
      trigger.cooldownInput.setValue(String(item.cooldown_minutes));
    }
  }, [
    setCreateMode,
    setCreateError,
    setCreateFocus,
    setCreateWritable,
    nameInput,
    model,
    setCreateDesc,
    setCreateDescCursor,
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
    createCustomDays: trigger.createCustomDays,
    createDayCursor: trigger.createDayCursor,
    triggersList,
    triggerCursor,
    editingTriggerIndex,
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
    idleMinutesInput: trigger.idleMinutesInput,
    everyNInput: trigger.everyNInput,
    cooldownInput: trigger.cooldownInput,
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
    setCreateCustomDays: trigger.setCreateCustomDays,
    setCreateDayCursor: trigger.setCreateDayCursor,
    setTriggersList,
    setTriggerCursor,
    setEditingTriggerIndex,
    setCreateModelCustomOption: model.setCreateModelCustomOption,
    setCreateModelIndex: model.setCreateModelIndex,
    setShowModelDropdown: model.setShowModelDropdown,
    setCreateDesc,
    setCreateDescCursor,
    enterTriggerEditor,
    addTrigger,
    removeTrigger,
    saveTriggerEdit,

    resetCreateState,
    getCreateValidationError,
    getTriggerValidationError,
    openFullEditor,
    parseLeadToMinutes: trigger.parseLeadToMinutes,
  };
}
