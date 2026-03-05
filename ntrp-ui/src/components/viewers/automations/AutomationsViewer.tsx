import React, { useState } from "react";
import type { Config } from "../../../types.js";
import { Dialog, Loading, colors, BaseSelectionList, Hints, SelectList } from "../../ui/index.js";
import { useAutomations } from "../../../hooks/useAutomations.js";
import { useAutomationForm } from "../../../hooks/useAutomationForm.js";
import { useAutomationKeypress } from "../../../hooks/useAutomationKeypress.js";
import { AutomationItem } from "./AutomationItem.js";
import { AutomationCreateView } from "./AutomationCreateView.js";
import { ResultViewer } from "./ResultViewer.js";

const DEFAULT_MODEL_OPTION = "__default__";

interface AutomationsViewerProps {
  config: Config;
  onClose: () => void;
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

  const form = useAutomationForm({
    availableModels,
    setCreateMode,
    setCreateError,
  });

  useAutomationKeypress({
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
  });

  const {
    editingTaskId,
    createFocus,
    createEditing,
    createTriggerType,
    createScheduleMode,
    createDaysOption,
    createEventType,
    createWritable,
    createNotifiers,
    createNotifierCursor,
    createCustomDays,
    createDayCursor,
    createModelIndex,
    showModelDropdown,
    createDesc,
    createDescCursor,
    createModelOptions,
    selectedModel,
    nameInput,
    timeInput,
    intervalInput,
    startInput,
    endInput,
    eventLeadInput,
    setCreateModelIndex,
    setShowModelDropdown,
    getCreateValidationError,
  } = form;

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
        items={createEditing
          ? [["type", "input"], ["esc", "done"], [createCanSave ? "^s" : "^S(off)", "save"]]
          : [["↑↓", "navigate"], ["enter", "edit"], ["←→", "adjust"], [createCanSave ? "^s" : "^S(off)", "save"], ["esc", "cancel"]]
        }
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
              editing={createEditing}
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
