import { useState, useCallback } from "react";
import { useInlineTextInput } from "./useInlineTextInput.js";

export type TriggerType = "time" | "event" | "idle" | "count";

export interface TriggerState {
  createTriggerType: TriggerType;
  createScheduleMode: "schedule" | "interval";
  createDaysOption: string;
  createEventType: string;
  createCustomDays: string[];
  createDayCursor: number;
  timeInput: ReturnType<typeof useInlineTextInput>;
  intervalInput: ReturnType<typeof useInlineTextInput>;
  startInput: ReturnType<typeof useInlineTextInput>;
  endInput: ReturnType<typeof useInlineTextInput>;
  eventLeadInput: ReturnType<typeof useInlineTextInput>;
  idleMinutesInput: ReturnType<typeof useInlineTextInput>;
  everyNInput: ReturnType<typeof useInlineTextInput>;
  cooldownInput: ReturnType<typeof useInlineTextInput>;
  setCreateTriggerType: React.Dispatch<React.SetStateAction<TriggerType>>;
  setCreateScheduleMode: React.Dispatch<React.SetStateAction<"schedule" | "interval">>;
  setCreateDaysOption: React.Dispatch<React.SetStateAction<string>>;
  setCreateEventType: React.Dispatch<React.SetStateAction<string>>;
  setCreateCustomDays: React.Dispatch<React.SetStateAction<string[]>>;
  setCreateDayCursor: React.Dispatch<React.SetStateAction<number>>;
  parseLeadToMinutes: (raw: string) => number | null;
  resetTriggerState: () => void;
}

export function useAutomationTriggerState(): TriggerState {
  const [createTriggerType, setCreateTriggerType] = useState<TriggerType>("time");
  const [createScheduleMode, setCreateScheduleMode] = useState<"schedule" | "interval">("schedule");
  const [createDaysOption, setCreateDaysOption] = useState("once");
  const [createEventType, setCreateEventType] = useState("event_approaching");
  const [createCustomDays, setCreateCustomDays] = useState<string[]>([]);
  const [createDayCursor, setCreateDayCursor] = useState(0);

  const timeInput = useInlineTextInput();
  const intervalInput = useInlineTextInput();
  const startInput = useInlineTextInput();
  const endInput = useInlineTextInput();
  const eventLeadInput = useInlineTextInput();
  const idleMinutesInput = useInlineTextInput();
  const everyNInput = useInlineTextInput();
  const cooldownInput = useInlineTextInput();

  const parseLeadToMinutes = useCallback((raw: string): number | null => {
    const normalized = raw.trim().toLowerCase();
    if (!normalized) return null;
    if (/^\d+$/.test(normalized)) return Number(normalized);
    const m = /^(?:(\d+)h)?(?:(\d+)m)?$/.exec(normalized);
    if (!m || (!m[1] && !m[2])) return null;
    const hours = Number(m[1] || 0);
    const mins = Number(m[2] || 0);
    const total = (hours * 60) + mins;
    return total > 0 ? total : null;
  }, []);

  const resetTriggerState = useCallback(() => {
    setCreateTriggerType("time");
    setCreateScheduleMode("schedule");
    setCreateDaysOption("once");
    setCreateEventType("event_approaching");
    setCreateCustomDays([]);
    setCreateDayCursor(0);
    timeInput.reset();
    intervalInput.reset();
    startInput.reset();
    endInput.reset();
    eventLeadInput.reset();
    eventLeadInput.setValue("60m");
    idleMinutesInput.reset();
    idleMinutesInput.setValue("5");
    everyNInput.reset();
    everyNInput.setValue("10");
    cooldownInput.reset();
  }, [timeInput, intervalInput, startInput, endInput, eventLeadInput, idleMinutesInput, everyNInput, cooldownInput]);

  return {
    createTriggerType,
    createScheduleMode,
    createDaysOption,
    createEventType,
    createCustomDays,
    createDayCursor,
    timeInput,
    intervalInput,
    startInput,
    endInput,
    eventLeadInput,
    idleMinutesInput,
    everyNInput,
    cooldownInput,
    setCreateTriggerType,
    setCreateScheduleMode,
    setCreateDaysOption,
    setCreateEventType,
    setCreateCustomDays,
    setCreateDayCursor,
    parseLeadToMinutes,
    resetTriggerState,
  };
}
