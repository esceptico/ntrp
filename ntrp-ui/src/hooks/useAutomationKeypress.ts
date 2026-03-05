import { useCallback } from "react";
import type { Automation, CreateAutomationData, NotifierSummary } from "../api/client.js";
import { useKeypress, type Key } from "./useKeypress.js";
import type { AutomationFormState } from "./useAutomationForm.js";
import { buildAutomationPayload, createFocusOrder } from "./useAutomationForm.js";
import {
  DAY_NAMES,
  EVENT_TYPES,
  SCHEDULE_DAYS,
  INTERVAL_DAYS,
  type CreateFocus,
} from "../components/viewers/automations/AutomationCreateView.js";

interface UseAutomationKeypressParams {
  form: AutomationFormState;
  automations: Automation[];
  selectedIndex: number;
  confirmDelete: boolean;
  viewingResult: Automation | null;
  createMode: boolean;
  saving: boolean;
  availableNotifiers: NotifierSummary[];
  setSelectedIndex: React.Dispatch<React.SetStateAction<number>>;
  setConfirmDelete: React.Dispatch<React.SetStateAction<boolean>>;
  setViewingResult: React.Dispatch<React.SetStateAction<Automation | null>>;
  setDetailScroll: React.Dispatch<React.SetStateAction<number>>;
  setLoading: React.Dispatch<React.SetStateAction<boolean>>;
  setCreateMode: React.Dispatch<React.SetStateAction<boolean>>;
  setCreateError: React.Dispatch<React.SetStateAction<string | null>>;
  onClose: () => void;
  handleToggle: () => Promise<void>;
  handleDelete: () => Promise<void>;
  handleToggleWritable: () => Promise<void>;
  handleRun: () => Promise<void>;
  handleViewResult: () => Promise<void>;
  handleCreate: (data: CreateAutomationData) => Promise<void>;
  handleUpdate: (taskId: string, data: CreateAutomationData) => Promise<void>;
  loadAutomations: () => Promise<void>;
}

export function useAutomationKeypress({
  form,
  automations,
  selectedIndex,
  confirmDelete,
  viewingResult,
  createMode,
  saving,
  availableNotifiers,
  setSelectedIndex,
  setConfirmDelete,
  setViewingResult,
  setDetailScroll,
  setLoading,
  setCreateMode,
  setCreateError,
  onClose,
  handleToggle,
  handleDelete,
  handleToggleWritable,
  handleRun,
  handleViewResult,
  handleCreate,
  handleUpdate,
  loadAutomations,
}: UseAutomationKeypressParams) {
  const {
    editingTaskId,
    createFocus,
    createEditing,
    createTriggerType,
    createScheduleMode,
    createDaysOption,
    createEventType,
    createNotifiers,
    createNotifierCursor,
    createCustomDays,
    createDayCursor,
    createWritable,
    createDesc,
    selectedModel,
    nameInput,
    descInput,
    timeInput,
    intervalInput,
    startInput,
    endInput,
    eventLeadInput,
    parseLeadToMinutes,
    setCreateFocus,
    setCreateEditing,
    setCreateTriggerType,
    setCreateScheduleMode,
    setCreateDaysOption,
    setCreateEventType,
    setCreateWritable,
    setCreateNotifiers,
    setCreateNotifierCursor,
    setCreateCustomDays,
    setCreateDayCursor,
    setEditingTaskId,
    setCreateModelCustomOption,
    setCreateModelIndex,
    setShowModelDropdown,
    setCreateDesc,
    setCreateDescCursor,
    resetCreateState,
    getCreateValidationError,
    openFullEditor,
    showModelDropdown,
  } = form;

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
        // Ctrl+S saves from any state
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
            handleUpdate(editingTaskId, data as CreateAutomationData);
          } else {
            handleCreate(data as CreateAutomationData);
          }
          return;
        }

        // Escape: undrill or exit
        if (key.name === "escape") {
          if (createEditing) {
            setCreateEditing(false);
          } else {
            resetCreateState();
          }
          return;
        }

        // --- Drilled into a field ---
        if (createEditing) {
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
          } else if (createFocus === "notifiers") {
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
          } else if (createFocus === "name") {
            nameInput.handleKey(key);
          } else if (createFocus === "description") {
            descInput.handleKey(key);
          } else if (createFocus === "time") {
            timeInput.handleKey(key);
          } else if (createFocus === "interval") {
            intervalInput.handleKey(key);
          } else if (createFocus === "start") {
            startInput.handleKey(key);
          } else if (createFocus === "end") {
            endInput.handleKey(key);
          } else if (createFocus === "event_lead") {
            eventLeadInput.handleKey(key);
          }
          return;
        }

        // --- Navigation mode (not editing) ---
        const focusOrder = createFocusOrder({
          triggerType: createTriggerType,
          scheduleMode: createScheduleMode,
          daysOption: createDaysOption,
          eventType: createEventType,
          hasNotifiers: availableNotifiers.length > 0,
        });
        const focusIdx = focusOrder.indexOf(createFocus);

        // up/down navigate fields
        if (key.name === "up" || key.name === "k") {
          if (focusIdx > 0) setCreateFocus(focusOrder[focusIdx - 1]);
          return;
        }
        if (key.name === "down" || key.name === "j") {
          if (focusIdx < focusOrder.length - 1) setCreateFocus(focusOrder[focusIdx + 1]);
          return;
        }

        // left/right for selector fields
        if (key.name === "left" || key.name === "h" || key.name === "right" || key.name === "l") {
          if (createFocus === "trigger_type") {
            setCreateTriggerType((t) => t === "time" ? "event" : "time");
          } else if (createFocus === "mode") {
            setCreateScheduleMode((m) => m === "schedule" ? "interval" : "schedule");
            setCreateDaysOption((d) => {
              if (d === "once") return "always";
              if (d === "always") return "once";
              return d;
            });
          } else if (createFocus === "days") {
            const opts: string[] = createScheduleMode === "schedule" ? [...SCHEDULE_DAYS] : [...INTERVAL_DAYS];
            if (key.name === "left" || key.name === "h") {
              setCreateDaysOption((d) => {
                const idx = opts.indexOf(d);
                return opts[Math.max(0, idx - 1)] ?? d;
              });
            } else {
              setCreateDaysOption((d) => {
                const idx = opts.indexOf(d);
                return opts[Math.min(opts.length - 1, idx + 1)] ?? d;
              });
            }
          } else if (createFocus === "event_type") {
            const types = EVENT_TYPES;
            setCreateEventType((t) => {
              const i = types.indexOf(t as typeof types[number]);
              return types[(i + 1) % types.length];
            });
          } else if (createFocus === "writable") {
            setCreateWritable((w) => !w);
          }
          return;
        }

        // Enter/Space: drill into field or toggle
        if (key.name === "return" || key.name === "space") {
          const textFields: CreateFocus[] = ["name", "description", "time", "interval", "start", "end", "event_lead"];
          const listFields: CreateFocus[] = ["notifiers", "day_picker"];
          if (textFields.includes(createFocus) || listFields.includes(createFocus)) {
            setCreateEditing(true);
          } else if (createFocus === "model") {
            setShowModelDropdown(true);
          } else if (createFocus === "writable") {
            setCreateWritable((w) => !w);
          }
          // selectors: no-op on Enter (use left/right)
          return;
        }
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
        resetCreateState();
        setCreateMode(true);
        setCreateFocus("name");
      }
    },
    [
      onClose, automations, selectedIndex, handleToggle, handleToggleWritable,
      confirmDelete, handleDelete, loadAutomations, handleViewResult, handleRun,
      viewingResult, createMode, createFocus, createEditing, createTriggerType, createScheduleMode,
      createDaysOption, createEventType, createNotifierCursor, createCustomDays, createDayCursor,
      selectedModel,
      handleCreate, handleUpdate, resetCreateState, getCreateValidationError,
      openFullEditor, editingTaskId,
      setSelectedIndex, setConfirmDelete, setViewingResult,
      setLoading, setCreateMode, setCreateFocus, setCreateEditing, setCreateTriggerType,
      setCreateScheduleMode, setCreateDaysOption, setCreateEventType, setCreateWritable,
      setCreateNotifiers, setCreateNotifierCursor, setCreateCustomDays, setCreateDayCursor, setEditingTaskId,
      setCreateError,
      nameInput, descInput, timeInput, intervalInput, startInput, endInput, eventLeadInput, parseLeadToMinutes,
      availableNotifiers,
      setDetailScroll, setCreateModelCustomOption, setCreateModelIndex, setShowModelDropdown,
      setCreateDesc, setCreateDescCursor, createNotifiers, createWritable, createDesc,
      saving,
    ]
  );

  useKeypress(handleKeypress, { isActive: !showModelDropdown });
}
