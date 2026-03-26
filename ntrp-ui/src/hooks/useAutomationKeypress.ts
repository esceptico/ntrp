import { useCallback } from "react";
import type { Automation, CreateAutomationData } from "../api/client.js";
import { useKeypress, type Key } from "./useKeypress.js";
import type { AutomationFormState } from "./useAutomationForm.js";
import { buildAutomationPayload, createFocusOrder } from "./useAutomationForm.js";
import {
  DAY_NAMES,
  EVENT_TYPES,
  TRIGGER_TYPES,
  SCHEDULE_DAYS,
  INTERVAL_DAYS,
  type CreateFocus,
} from "../components/viewers/automations/AutomationCreateView.js";
import type { AutomationTab } from "./useAutomations.js";

interface UseAutomationKeypressParams {
  form: AutomationFormState;
  automations: Automation[];
  selectedIndex: number;
  confirmDelete: boolean;
  viewingResult: Automation | null;
  createMode: boolean;
  saving: boolean;
  activeTab: AutomationTab;
  setSelectedIndex: React.Dispatch<React.SetStateAction<number>>;
  setConfirmDelete: React.Dispatch<React.SetStateAction<boolean>>;
  setViewingResult: React.Dispatch<React.SetStateAction<Automation | null>>;
  setDetailScroll: React.Dispatch<React.SetStateAction<number>>;
  setLoading: React.Dispatch<React.SetStateAction<boolean>>;
  setCreateMode: React.Dispatch<React.SetStateAction<boolean>>;
  setCreateError: React.Dispatch<React.SetStateAction<string | null>>;
  setActiveTab: React.Dispatch<React.SetStateAction<AutomationTab>>;
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
  activeTab,
  setSelectedIndex,
  setConfirmDelete,
  setViewingResult,
  setDetailScroll,
  setLoading,
  setCreateMode,
  setCreateError,
  setActiveTab,
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
    createCustomDays,
    createDayCursor,
    createWritable,
    triggersList,
    triggerCursor,
    editingTriggerIndex,
    createDesc,
    selectedModel,
    nameInput,
    descInput,
    timeInput,
    intervalInput,
    startInput,
    endInput,
    eventLeadInput,
    idleMinutesInput,
    everyNInput,
    cooldownInput,
    parseLeadToMinutes,
    setCreateFocus,
    setCreateEditing,
    setCreateTriggerType,
    setCreateScheduleMode,
    setCreateDaysOption,
    setCreateEventType,
    setCreateWritable,
    setCreateCustomDays,
    setCreateDayCursor,
    setTriggerCursor,
    setEditingTaskId,
    setCreateModelCustomOption,
    setCreateModelIndex,
    setShowModelDropdown,
    setCreateDesc,
    setCreateDescCursor,
    enterTriggerEditor,
    addTrigger,
    removeTrigger,
    saveTriggerEdit,
    resetCreateState,
    getCreateValidationError,
    openFullEditor,
    showModelDropdown,
  } = form;

  const isEditingTrigger = editingTriggerIndex !== null;

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

      // Create/edit mode
      if (createMode) {
        // Ctrl+S saves the whole automation
        if (key.ctrl && key.name === "s") {
          // If editing a trigger, save it first
          if (isEditingTrigger) {
            saveTriggerEdit();
          }
          const validationError = getCreateValidationError();
          if (validationError) {
            setCreateError(validationError);
            return;
          }
          const cooldown = Number(cooldownInput.value) || undefined;
          const data = buildAutomationPayload({
            name: nameInput.value.trim(),
            description: createDesc.trim(),
            model: selectedModel,
            writable: createWritable,
            triggers: triggersList,
            cooldown_minutes: cooldown,
          });
          if (editingTaskId) {
            handleUpdate(editingTaskId, data);
          } else {
            handleCreate(data);
          }
          return;
        }

        // === Trigger editor mode ===
        if (isEditingTrigger) {
          // Escape: save trigger and return to triggers list
          if (key.name === "escape") {
            if (createEditing) {
              setCreateEditing(false);
            } else {
              saveTriggerEdit();
            }
            return;
          }

          // Drilled into a text field
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
            } else if (createFocus === "idle_minutes") {
              idleMinutesInput.handleKey(key);
            } else if (createFocus === "every_n") {
              everyNInput.handleKey(key);
            }
            return;
          }

          // Navigation within trigger editor
          const triggerFocusOrder = createFocusOrder({
            editingTrigger: true,
            triggerType: createTriggerType,
            scheduleMode: createScheduleMode,
            daysOption: createDaysOption,
            eventType: createEventType,
          });
          const triggerFocusIdx = triggerFocusOrder.indexOf(createFocus);

          if (key.name === "up" || key.name === "k") {
            if (triggerFocusIdx > 0) setCreateFocus(triggerFocusOrder[triggerFocusIdx - 1]);
            return;
          }
          if (key.name === "down" || key.name === "j") {
            if (triggerFocusIdx < triggerFocusOrder.length - 1) setCreateFocus(triggerFocusOrder[triggerFocusIdx + 1]);
            return;
          }

          // Left/right for selectors
          if (key.name === "left" || key.name === "h" || key.name === "right" || key.name === "l") {
            if (createFocus === "trigger_type") {
              const dir = (key.name === "right" || key.name === "l") ? 1 : -1;
              setCreateTriggerType((t) => {
                const idx = TRIGGER_TYPES.indexOf(t as typeof TRIGGER_TYPES[number]);
                const next = (idx + dir + TRIGGER_TYPES.length) % TRIGGER_TYPES.length;
                return TRIGGER_TYPES[next];
              });
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
            }
            return;
          }

          // Enter: drill into text fields
          if (key.name === "return" || key.name === "space") {
            const textFields: CreateFocus[] = ["time", "interval", "start", "end", "event_lead", "idle_minutes", "every_n"];
            const listFields: CreateFocus[] = ["day_picker"];
            if (textFields.includes(createFocus) || listFields.includes(createFocus)) {
              setCreateEditing(true);
            }
          }
          return;
        }

        // === Main form mode (not editing trigger) ===

        // Escape: undrill or exit form
        if (key.name === "escape") {
          if (createEditing) {
            setCreateEditing(false);
          } else {
            resetCreateState();
          }
          return;
        }

        // Drilled into a main field
        if (createEditing) {
          if (createFocus === "name") {
            nameInput.handleKey(key);
          } else if (createFocus === "description") {
            descInput.handleKey(key);
          } else if (createFocus === "cooldown") {
            cooldownInput.handleKey(key);
          }
          return;
        }

        // Navigation in main form
        const mainFocusOrder = createFocusOrder({
          editingTrigger: false,
          triggerType: createTriggerType,
          scheduleMode: createScheduleMode,
          daysOption: createDaysOption,
          eventType: createEventType,
        });
        const mainFocusIdx = mainFocusOrder.indexOf(createFocus);

        if (key.name === "up" || key.name === "k") {
          if (createFocus === "triggers_list" && triggerCursor > 0) {
            setTriggerCursor((c) => c - 1);
          } else if (mainFocusIdx > 0) {
            const prev = mainFocusOrder[mainFocusIdx - 1];
            setCreateFocus(prev);
            if (prev === "triggers_list") setTriggerCursor(Math.max(0, triggersList.length - 1));
          }
          return;
        }
        if (key.name === "down" || key.name === "j") {
          if (createFocus === "triggers_list" && triggerCursor < triggersList.length - 1) {
            setTriggerCursor((c) => c + 1);
          } else if (mainFocusIdx < mainFocusOrder.length - 1) {
            const next = mainFocusOrder[mainFocusIdx + 1];
            setCreateFocus(next);
            if (next === "triggers_list") setTriggerCursor(0);
          }
          return;
        }

        // Left/right on writable
        if (key.name === "left" || key.name === "h" || key.name === "right" || key.name === "l") {
          if (createFocus === "writable") {
            setCreateWritable((w) => !w);
          }
          return;
        }

        // Enter/Space: context-dependent
        if (key.name === "return" || key.name === "space") {
          if (createFocus === "triggers_list") {
            if (triggersList.length > 0) {
              enterTriggerEditor(triggerCursor);
            }
          } else if (createFocus === "name" || createFocus === "description" || createFocus === "cooldown") {
            setCreateEditing(true);
          } else if (createFocus === "model") {
            setShowModelDropdown(true);
          } else if (createFocus === "writable") {
            setCreateWritable((w) => !w);
          }
          return;
        }

        // Triggers list: a=add, d=remove
        if (createFocus === "triggers_list") {
          if (key.name === "a" || key.sequence === "+") {
            addTrigger();
            return;
          }
          if ((key.name === "d" || key.sequence === "-") && triggersList.length > 0) {
            removeTrigger();
            return;
          }
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
      } else if (key.name === "tab") {
        setActiveTab((t) => t === "user" ? "internal" : "user");
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
      } else if (key.name === "d" && activeTab === "user") {
        const selected = automations[selectedIndex];
        if (automations.length > 0 && selected && !selected.builtin) setConfirmDelete(true);
      } else if (key.name === "w") {
        handleToggleWritable();
      } else if (key.name === "x") {
        handleRun();
      } else if (key.name === "r") {
        setLoading(true);
        loadAutomations();
      } else if (key.name === "n" && activeTab === "user") {
        resetCreateState();
        setCreateMode(true);
        setCreateFocus("name");
      }
    },
    [
      onClose, automations, selectedIndex, activeTab, handleToggle, handleToggleWritable,
      confirmDelete, handleDelete, loadAutomations, handleViewResult, handleRun, setActiveTab,
      viewingResult, createMode, createFocus, createEditing, isEditingTrigger,
      createTriggerType, createScheduleMode,
      createDaysOption, createEventType, createCustomDays, createDayCursor,
      selectedModel, triggersList, triggerCursor, editingTriggerIndex,
      handleCreate, handleUpdate, resetCreateState, getCreateValidationError,
      enterTriggerEditor, addTrigger, removeTrigger, saveTriggerEdit,
      openFullEditor, editingTaskId,
      setSelectedIndex, setConfirmDelete, setViewingResult,
      setLoading, setCreateMode, setCreateFocus, setCreateEditing, setCreateTriggerType,
      setCreateScheduleMode, setCreateDaysOption, setCreateEventType, setCreateWritable,
      setCreateCustomDays, setCreateDayCursor,
      setTriggerCursor, setEditingTaskId, setCreateError,
      nameInput, descInput, timeInput, intervalInput, startInput, endInput,
      eventLeadInput, idleMinutesInput, everyNInput, cooldownInput, parseLeadToMinutes,
      setDetailScroll, setCreateModelCustomOption, setCreateModelIndex, setShowModelDropdown,
      setCreateDesc, setCreateDescCursor, createWritable, createDesc,
      saving,
    ]
  );

  useKeypress(handleKeypress, { isActive: !showModelDropdown });
}
