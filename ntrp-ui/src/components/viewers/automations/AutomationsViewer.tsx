import React, { useState, useCallback, useMemo } from "react";
import type { Config } from "../../../types.js";
import type { Automation, CreateAutomationData, UpdateAutomationData } from "../../../api/client.js";
import { useKeypress, type Key } from "../../../hooks/index.js";
import { useInlineTextInput } from "../../../hooks/useInlineTextInput.js";
import { useTextInput } from "../../../hooks/useTextInput.js";
import { Dialog, Loading, colors, BaseSelectionList, Hints, SelectList } from "../../ui/index.js";
import { useAutomations } from "../../../hooks/useAutomations.js";
import { AutomationItem } from "./AutomationItem.js";
import {
  AutomationCreateView,
  SCHEDULE_DAYS,
  INTERVAL_DAYS,
  DAY_NAMES,
  EVENT_TYPES,
  type CreateFocus,
} from "./AutomationCreateView.js";
import { ResultViewer } from "./ResultViewer.js";

interface AutomationsViewerProps {
  config: Config;
  onClose: () => void;
}

const DEFAULT_MODEL_OPTION = "__default__";

function buildAutomationPayload(params: {
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

function createFocusOrder(params: {
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

export function AutomationsViewer({ config, onClose }: AutomationsViewerProps) {
  const {
    automations,
    selectedIndex,
    loading,
    error,
    confirmDelete,
    viewingResult,
    saving,
    createMode,
    createError,
    setSelectedIndex,
    setConfirmDelete,
    setViewingResult,
    setLoading,
    setCreateMode,
    setCreateError,
    loadAutomations,
    handleToggle,
    handleDelete,
    handleToggleWritable,
    handleRun,
    handleViewResult,
    handleCreate,
    handleUpdate,
    availableNotifiers,
    availableModels,
  } = useAutomations(config);

  const [detailScroll, setDetailScroll] = useState(0);

  const [editingTaskId, setEditingTaskId] = useState<string | null>(null);

  // Create mode state
  const [createFocus, setCreateFocus] = useState<CreateFocus>("name");
  const [createTriggerType, setCreateTriggerType] = useState<"time" | "event">("time");
  const [createScheduleMode, setCreateScheduleMode] = useState<"schedule" | "interval">("schedule");
  const [createDaysOption, setCreateDaysOption] = useState("once");
  const [createEventType, setCreateEventType] = useState("event_approaching");
  const [createWritable, setCreateWritable] = useState(false);
  const [createNotifiers, setCreateNotifiers] = useState<string[]>([]);
  const [createNotifierCursor, setCreateNotifierCursor] = useState(0);
  const [createCustomDays, setCreateCustomDays] = useState<string[]>([]);
  const [createDayCursor, setCreateDayCursor] = useState(0);
  const [createModelCustomOption, setCreateModelCustomOption] = useState<string | null>(null);
  const [createModelIndex, setCreateModelIndex] = useState(0);
  const [showModelDropdown, setShowModelDropdown] = useState(false);

  // Controlled inputs for create form (so preview stays in sync)
  const nameInput = useInlineTextInput();
  const [createDesc, setCreateDesc] = useState("");
  const [createDescCursor, setCreateDescCursor] = useState(0);
  const descInput = useTextInput({
    text: createDesc,
    cursorPos: createDescCursor,
    setText: setCreateDesc,
    setCursorPos: setCreateDescCursor,
  });
  const timeInput = useInlineTextInput();
  const intervalInput = useInlineTextInput();
  const startInput = useInlineTextInput();
  const endInput = useInlineTextInput();
  const eventLeadInput = useInlineTextInput();

  const createModelOptions = useMemo(() => {
    const base = [DEFAULT_MODEL_OPTION, ...availableModels];
    if (createModelCustomOption && !base.includes(createModelCustomOption)) {
      base.push(createModelCustomOption);
    }
    return base;
  }, [availableModels, createModelCustomOption]);

  const selectedModel = createModelOptions[createModelIndex] === DEFAULT_MODEL_OPTION
    ? ""
    : (createModelOptions[createModelIndex] ?? "");

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

  const resetCreateState = useCallback(() => {
    setEditingTaskId(null);
    setCreateMode(false);
    setCreateFocus("name");
    setCreateTriggerType("time");
    setCreateScheduleMode("schedule");
    setCreateDaysOption("once");
    setCreateEventType("event_approaching");
    setCreateWritable(false);
    setCreateNotifiers([]);
    setCreateNotifierCursor(0);
    setCreateCustomDays([]);
    setCreateDayCursor(0);
    setCreateModelCustomOption(null);
    setCreateModelIndex(0);
    setShowModelDropdown(false);
    setCreateError(null);
    nameInput.reset();
    setCreateDesc("");
    setCreateDescCursor(0);
    timeInput.reset();
    intervalInput.reset();
    startInput.reset();
    endInput.reset();
    eventLeadInput.reset();
    eventLeadInput.setValue("60m");
  }, [
    setEditingTaskId,
    setCreateMode,
    setCreateError,
    nameInput,
    timeInput,
    intervalInput,
    startInput,
    endInput,
    eventLeadInput,
  ]);

  const getCreateValidationError = useCallback((): string | null => {
    const name = nameInput.value.trim();
    const description = createDesc.trim();
    if (!name || !description) return "Name and description are required";
    if (createTriggerType === "time") {
      if (createScheduleMode === "schedule") {
        const at = timeInput.value.trim();
        if (!at) return "Time is required for schedule mode";
      } else {
        const every = intervalInput.value.trim();
        if (!every) return "Interval is required for interval mode";
        const start = startInput.value.trim();
        const end = endInput.value.trim();
        if ((start && !end) || (!start && end)) return "Both start and end times are required";
      }
      if (createDaysOption === "custom" && createCustomDays.length === 0) {
        return "Select at least one day";
      }
    }
    if (createTriggerType === "event" && createEventType === "event_approaching") {
      const lead = parseLeadToMinutes(eventLeadInput.value);
      if (lead === null) return "Lead time must be like 30m or 2h30m";
    }
    return null;
  }, [
    createTriggerType,
    createScheduleMode,
    createDaysOption,
    createCustomDays,
    nameInput.value,
    createDesc,
    timeInput.value,
    intervalInput.value,
    startInput.value,
    endInput.value,
    createEventType,
    eventLeadInput.value,
    parseLeadToMinutes,
  ]);

  const openFullEditor = useCallback((item: Automation) => {
    setEditingTaskId(item.task_id);
    setCreateMode(true);
    setCreateError(null);
    setCreateFocus("name");

    nameInput.reset();
    nameInput.setValue(item.name ?? "");
    const model = item.model ?? "";
    if (model && !createModelOptions.includes(model)) {
      setCreateModelCustomOption(model);
      setCreateModelIndex(createModelOptions.length);
    } else {
      setCreateModelCustomOption(null);
      const idx = createModelOptions.indexOf(model || DEFAULT_MODEL_OPTION);
      setCreateModelIndex(idx >= 0 ? idx : 0);
    }
    setCreateDesc(item.description ?? "");
    setCreateDescCursor((item.description ?? "").length);

    setCreateNotifiers(item.notifiers ?? []);
    setCreateNotifierCursor(0);
    setCreateWritable(item.writable);
    setCreateCustomDays([]);
    setCreateDayCursor(0);

    if (item.trigger.type === "event") {
      setCreateTriggerType("event");
      setCreateEventType(item.trigger.event_type);
      eventLeadInput.reset();
      eventLeadInput.setValue(`${item.trigger.lead_minutes ?? 60}m`);
      setCreateScheduleMode("schedule");
      setCreateDaysOption("once");
      timeInput.reset();
      intervalInput.reset();
      startInput.reset();
      endInput.reset();
      return;
    }

    setCreateTriggerType("time");
    if (item.trigger.every) {
      setCreateScheduleMode("interval");
      intervalInput.reset();
      intervalInput.setValue(item.trigger.every);
      startInput.reset();
      endInput.reset();
      if (item.trigger.start) startInput.setValue(item.trigger.start);
      if (item.trigger.end) endInput.setValue(item.trigger.end);
      timeInput.reset();
    } else {
      setCreateScheduleMode("schedule");
      timeInput.reset();
      if (item.trigger.at) timeInput.setValue(item.trigger.at);
      intervalInput.reset();
      startInput.reset();
      endInput.reset();
    }

    const rawDays = item.trigger.days;
    const scheduleDefault = item.trigger.every ? "always" : "once";
    const allowed = item.trigger.every ? INTERVAL_DAYS : SCHEDULE_DAYS;
    if (!rawDays) {
      setCreateDaysOption(scheduleDefault);
    } else if ((allowed as readonly string[]).includes(rawDays)) {
      setCreateDaysOption(rawDays);
    } else {
      setCreateDaysOption("custom");
      setCreateCustomDays(rawDays.split(",").map((d) => d.trim()).filter(Boolean));
    }
  }, [
    setEditingTaskId,
    setCreateMode,
    setCreateError,
    setCreateFocus,
    setCreateNotifiers,
    setCreateNotifierCursor,
    setCreateWritable,
    setCreateCustomDays,
    setCreateDayCursor,
    setCreateTriggerType,
    setCreateEventType,
    setCreateScheduleMode,
    setCreateDaysOption,
    nameInput,
    createModelOptions,
    setCreateDesc,
    setCreateDescCursor,
    timeInput,
    intervalInput,
    startInput,
    endInput,
    eventLeadInput,
  ]);

  const handleKeypress = useCallback(
    (key: Key) => {
      // Detail view mode
      if (viewingResult) {
        if (key.name === "escape" || key.name === "q") {
          setViewingResult(null);
          setDetailScroll(0);
          return;
        }
        if (key.name === "up" || key.name === "k") {
          setDetailScroll((s) => Math.max(0, s - 1));
        } else if (key.name === "down" || key.name === "j") {
          setDetailScroll((s) => s + 1);
        }
        return;
      }

      // Create mode
      if (createMode) {
        if (key.ctrl && key.name === "s") {
          const validationError = getCreateValidationError();
          if (validationError) {
            setCreateError(validationError);
            return;
          }
          const data = buildAutomationPayload({
            name: nameInput.value.trim(),
            description: createDesc.trim(),
            model: selectedModel,
            triggerType: createTriggerType,
            scheduleMode: createScheduleMode,
            time: timeInput.value.trim(),
            every: intervalInput.value.trim(),
            start: startInput.value.trim(),
            end: endInput.value.trim(),
            daysOption: createDaysOption,
            customDays: createCustomDays,
            eventType: createEventType,
            eventLead: parseLeadToMinutes(eventLeadInput.value) ?? 60,
            notifiers: createNotifiers,
            writable: createWritable,
          });
          if (editingTaskId) {
            handleUpdate(editingTaskId, data);
          } else {
            handleCreate(data as CreateAutomationData);
          }
          return;
        }
        if (key.name === "escape") {
          resetCreateState();
          return;
        }
        if (key.name === "tab") {
          setCreateFocus((f) => {
            const order = createFocusOrder({
              triggerType: createTriggerType,
              scheduleMode: createScheduleMode,
              daysOption: createDaysOption,
              eventType: createEventType,
              hasNotifiers: availableNotifiers.length > 0,
            });
            const idx = order.indexOf(f);
            return order[(idx + 1) % order.length];
          });
          return;
        }

        // Selector fields
        if (createFocus === "trigger_type") {
          if (key.name === "left" || key.name === "h" || key.name === "right" || key.name === "l") {
            setCreateTriggerType((t) => t === "time" ? "event" : "time");
          }
          return;
        }
        if (createFocus === "model") {
          if (key.name === "return" || key.name === "space") {
            setShowModelDropdown(true);
          }
          return;
        }
        if (createFocus === "mode") {
          if (key.name === "left" || key.name === "h" || key.name === "right" || key.name === "l") {
            setCreateScheduleMode((m) => m === "schedule" ? "interval" : "schedule");
            setCreateDaysOption((d) => {
              // Reset to a valid default when switching modes
              if (d === "once") return "always";
              if (d === "always") return "once";
              return d;
            });
          }
          return;
        }
        if (createFocus === "days") {
          const opts: string[] = createScheduleMode === "schedule" ? [...SCHEDULE_DAYS] : [...INTERVAL_DAYS];
          if (key.name === "left" || key.name === "h") {
            setCreateDaysOption((d) => {
              const idx = opts.indexOf(d);
              return opts[Math.max(0, idx - 1)] ?? d;
            });
          } else if (key.name === "right" || key.name === "l") {
            setCreateDaysOption((d) => {
              const idx = opts.indexOf(d);
              return opts[Math.min(opts.length - 1, idx + 1)] ?? d;
            });
          }
          return;
        }
        if (createFocus === "day_picker") {
          if (key.name === "left" || key.name === "h") {
            setCreateDayCursor((i) => Math.max(0, i - 1));
          } else if (key.name === "right" || key.name === "l") {
            setCreateDayCursor((i) => Math.min(DAY_NAMES.length - 1, i + 1));
          } else if (key.name === "space" || key.name === "return") {
            const day = DAY_NAMES[createDayCursor];
            if (day) {
              setCreateCustomDays((prev) =>
                prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day]
              );
            }
          }
          return;
        }
        if (createFocus === "event_type") {
          if (key.name === "left" || key.name === "h" || key.name === "right" || key.name === "l") {
            const types = EVENT_TYPES;
            setCreateEventType((t) => {
              const i = types.indexOf(t as typeof types[number]);
              return types[(i + 1) % types.length];
            });
          }
          return;
        }
        if (createFocus === "event_lead") {
          if (eventLeadInput.handleKey(key)) return;
          return;
        }
        if (createFocus === "notifiers") {
          if (key.name === "up" || key.name === "k") {
            setCreateNotifierCursor((i) => Math.max(0, i - 1));
          } else if (key.name === "down" || key.name === "j") {
            setCreateNotifierCursor((i) => Math.min(availableNotifiers.length - 1, i + 1));
          } else if (key.name === "space" || key.name === "return") {
            const notifier = availableNotifiers[createNotifierCursor];
            if (notifier) {
              setCreateNotifiers((prev) =>
                prev.includes(notifier.name) ? prev.filter((n) => n !== notifier.name) : [...prev, notifier.name]
              );
            }
          }
          return;
        }
        if (createFocus === "writable") {
          if (key.name === "space" || key.name === "return") {
            setCreateWritable((w) => !w);
          }
          return;
        }

        // Text fields: route to controlled input handlers
        if (createFocus === "name" && nameInput.handleKey(key)) return;
        if (createFocus === "description" && descInput.handleKey(key)) return;
        if (createFocus === "time" && timeInput.handleKey(key)) return;
        if (createFocus === "interval" && intervalInput.handleKey(key)) return;
        if (createFocus === "start" && startInput.handleKey(key)) return;
        if (createFocus === "end" && endInput.handleKey(key)) return;
        return;
      }

      // Delete confirmation
      if (confirmDelete) {
        if (key.name === "y") {
          handleDelete();
        } else {
          setConfirmDelete(false);
        }
        return;
      }

      // List mode
      if (key.name === "escape" || key.name === "q") {
        onClose();
      } else if (key.name === "up" || key.name === "k") {
        setSelectedIndex((i) => Math.max(0, i - 1));
      } else if (key.name === "down" || key.name === "j") {
        setSelectedIndex((i) => Math.min(automations.length - 1, i + 1));
      } else if (key.name === "space") {
        handleToggle();
      } else if (key.name === "return") {
        handleViewResult();
      } else if (key.name === "e") {
        const item = automations[selectedIndex];
        if (item) {
          openFullEditor(item);
        }
      } else if (key.name === "d") {
        if (automations.length > 0) setConfirmDelete(true);
      } else if (key.name === "w") {
        handleToggleWritable();
      } else if (key.name === "x") {
        handleRun();
      } else if (key.name === "r") {
        setLoading(true);
        loadAutomations();
      } else if (key.name === "n") {
        setEditingTaskId(null);
        nameInput.reset();
        setCreateModelCustomOption(null);
        setCreateModelIndex(0);
        setShowModelDropdown(false);
        eventLeadInput.reset();
        eventLeadInput.setValue("60m");
        setCreateDesc("");
        setCreateDescCursor(0);
        timeInput.reset();
        intervalInput.reset();
        startInput.reset();
        endInput.reset();
        setCreateMode(true);
        setCreateFocus("name");
      }
    },
    [
      onClose, automations, selectedIndex, handleToggle, handleToggleWritable,
      confirmDelete, handleDelete, loadAutomations, handleViewResult, handleRun,
      viewingResult, createMode, createFocus, createTriggerType, createScheduleMode,
      createDaysOption, createEventType, createNotifierCursor, createCustomDays, createDayCursor,
      createModelIndex, createModelOptions, selectedModel,
      handleCreate, handleUpdate, resetCreateState, getCreateValidationError,
      openFullEditor, editingTaskId,
      setSelectedIndex, setConfirmDelete, setViewingResult,
      setLoading, setCreateMode, setCreateFocus, setCreateTriggerType,
      setCreateScheduleMode, setCreateDaysOption, setCreateEventType, setCreateWritable,
      setCreateNotifiers, setCreateNotifierCursor, setCreateCustomDays, setCreateDayCursor, setEditingTaskId,
      setCreateError,
      nameInput, descInput, timeInput, intervalInput, startInput, endInput, eventLeadInput, parseLeadToMinutes,
    ]
  );

  useKeypress(handleKeypress, { isActive: !showModelDropdown });

  const createCanSave = createMode && !saving && getCreateValidationError() === null;

  if (showModelDropdown && createMode) {
    const currentModel = createModelOptions[createModelIndex] ?? DEFAULT_MODEL_OPTION;
    return (
      <Dialog title="AUTOMATION MODEL" size="medium" onClose={() => setShowModelDropdown(false)}>
        {({ width, height }) => (
          <SelectList
            options={createModelOptions.map(m => ({
              value: m,
              title: m,
              indicator: m === currentModel ? "●" : undefined,
            }))}
            search
            initialIndex={Math.max(0, createModelIndex)}
            visibleLines={height}
            width={Math.min(50, width)}
            onSelect={(opt) => {
              const idx = createModelOptions.indexOf(opt.value);
              if (idx >= 0) setCreateModelIndex(idx);
              setShowModelDropdown(false);
            }}
            onClose={() => setShowModelDropdown(false)}
          />
        )}
      </Dialog>
    );
  }

  const getFooter = (): React.ReactNode => {
    if (viewingResult) return <Hints items={[["j/k", "scroll"], ["q", "back"]]} />;
    if (createMode) return saving
      ? <text><span fg={colors.text.muted}>{editingTaskId ? "Updating..." : "Creating..."}</span></text>
      : <Hints
        items={[
          [createCanSave ? "^S" : "^S(disabled)", "save"],
          ["esc", "cancel"],
          ["tab", "next"],
          ["arrows", "move/select"],
          ["space", "toggle"],
        ]}
      />;
    if (confirmDelete) return <Hints items={[["y", "confirm"], ["n", "cancel"]]} />;
    return <Hints items={[["n", "new"], ["enter", "detail"], ["spc", "toggle"], ["e", "edit"], ["x", "run"], ["d", "del"]]} />;
  };

  if (loading) {
    return (
      <Dialog title="AUTOMATIONS" size="large" onClose={onClose}>
        {() => <Loading message="Loading automations..." />}
      </Dialog>
    );
  }

  if (error) {
    return (
      <Dialog title="AUTOMATIONS" size="large" onClose={onClose}>
        {() => <text><span fg={colors.status.error}>{error}</span></text>}
      </Dialog>
    );
  }

  return (
    <Dialog
      title="AUTOMATIONS"
      size="large"
      onClose={onClose}
      footer={getFooter()}
    >
      {({ width, height }) => {
        if (viewingResult) {
          return (
            <ResultViewer
              automation={viewingResult}
              scroll={detailScroll}
              setScroll={setDetailScroll}
              width={width}
              height={height}
            />
          );
        }

        if (createMode) {
          return (
            <AutomationCreateView
              focus={createFocus}
              triggerType={createTriggerType}
              scheduleMode={createScheduleMode}
              daysOption={createDaysOption}
              eventType={createEventType}
              eventLeadValue={eventLeadInput.value}
              eventLeadCursorPos={eventLeadInput.cursorPos}
              writable={createWritable}
              saving={saving}
              error={createError}
              width={width}
              availableNotifiers={availableNotifiers}
              notifiers={createNotifiers}
              notifierCursor={createNotifierCursor}
              customDays={createCustomDays}
              dayCursor={createDayCursor}
              nameValue={nameInput.value}
              nameCursorPos={nameInput.cursorPos}
              descValue={createDesc}
              descCursorPos={createDescCursor}
              selectedModel={selectedModel}
              timeValue={timeInput.value}
              timeCursorPos={timeInput.cursorPos}
              intervalValue={intervalInput.value}
              intervalCursorPos={intervalInput.cursorPos}
              startValue={startInput.value}
              startCursorPos={startInput.cursorPos}
              endValue={endInput.value}
              endCursorPos={endInput.cursorPos}
              canSave={createCanSave}
            />
          );
        }

        const visibleLines = Math.max(1, Math.floor((height - 2) / 4));

        return (
          <box flexDirection="column" height={height} overflow="hidden">
            <BaseSelectionList
              items={automations}
              selectedIndex={selectedIndex}
              renderItem={(item, context) => <AutomationItem item={item} context={context} textWidth={width - 2} />}
              visibleLines={visibleLines}
              emptyMessage="No automations. Press [n] to create one."
              getKey={(item) => item.task_id}
              width={width}
              indicator="▶"
              showScrollArrows
              showCount
            />

            {confirmDelete && automations[selectedIndex] && (
              <box marginTop={1}>
                <text>
                  <span fg={colors.status.warning}>
                    Delete "{automations[selectedIndex].description}"? (y/n)
                  </span>
                </text>
              </box>
            )}
          </box>
        );
      }}
    </Dialog>
  );
}
