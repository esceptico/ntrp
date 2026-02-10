import { useCallback } from "react";
import { Box, Text } from "ink";
import type { Config } from "../../../types.js";
import { useKeypress, useTextInput, type Key } from "../../../hooks/index.js";
import { useDimensions } from "../../../contexts/index.js";
import { Panel, Footer, Loading, colors, BaseSelectionList } from "../../ui/index.js";
import { VISIBLE_LINES } from "../../../lib/constants.js";
import { useSchedules, type EditFocus } from "../../../hooks/useSchedules.js";
import { ScheduleItem } from "./ScheduleItem.js";
import { ScheduleEditView } from "./ScheduleEditView.js";
import { ResultViewer } from "./ResultViewer.js";

interface SchedulesViewerProps {
  config: Config;
  onClose: () => void;
}

const FOCUS_ORDER: EditFocus[] = ["name", "description", "notifiers"];

export function SchedulesViewer({ config, onClose }: SchedulesViewerProps) {
  const { width: terminalWidth } = useDimensions();
  const contentWidth = Math.max(0, terminalWidth - 4);
  const textWidth = contentWidth - 2;

  const {
    schedules,
    selectedIndex,
    loading,
    error,
    confirmDelete,
    viewingResult,
    editMode,
    editName,
    editNameCursorPos,
    editText,
    cursorPos,
    saving,
    setSelectedIndex,
    setConfirmDelete,
    setViewingResult,
    setEditMode,
    setEditName,
    setEditNameCursorPos,
    setEditText,
    setCursorPos,
    setLoading,
    setEditFocus,
    setEditNotifiers,
    setEditNotifierCursor,
    loadSchedules,
    handleToggle,
    handleDelete,
    handleToggleWritable,
    handleRun,
    handleViewResult,
    handleSave,
    availableNotifiers,
    editFocus,
    editNotifiers,
    editNotifierCursor,
  } = useSchedules(config);

  const nameInput = useTextInput({
    text: editName,
    cursorPos: editNameCursorPos,
    setText: setEditName,
    setCursorPos: setEditNameCursorPos,
  });

  const textInput = useTextInput({
    text: editText,
    cursorPos,
    setText: setEditText,
    setCursorPos,
  });

  const handleKeypress = useCallback(
    (key: Key) => {
      // Edit mode handlers
      if (editMode) {
        if (key.ctrl && key.name === "s") {
          handleSave();
          return;
        }
        if (key.name === "escape") {
          setEditMode(false);
          setEditName("");
          setEditNameCursorPos(0);
          setEditText("");
          setCursorPos(0);
          setEditFocus("name");
          return;
        }
        if (key.name === "tab") {
          const sections = availableNotifiers.length > 0
            ? FOCUS_ORDER
            : FOCUS_ORDER.filter((f) => f !== "notifiers");
          setEditFocus((f) => {
            const idx = sections.indexOf(f);
            return sections[(idx + 1) % sections.length];
          });
          return;
        }

        if (editFocus === "notifiers") {
          if (key.name === "up" || key.name === "k") {
            setEditNotifierCursor((i) => Math.max(0, i - 1));
          } else if (key.name === "down" || key.name === "j") {
            setEditNotifierCursor((i) => Math.min(availableNotifiers.length - 1, i + 1));
          } else if (key.name === "space" || key.name === "return") {
            const name = availableNotifiers[editNotifierCursor];
            if (name) {
              setEditNotifiers((prev) =>
                prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name]
              );
            }
          }
          return;
        }

        if (editFocus === "name") {
          if (key.name !== "return") {
            nameInput.handleKey(key);
          }
          return;
        }

        // Description focus — delegate to text input
        textInput.handleKey(key);
        return;
      }

      // Delete confirmation handlers
      if (confirmDelete) {
        if (key.name === "y") {
          handleDelete();
        } else {
          setConfirmDelete(false);
        }
        return;
      }

      // List navigation handlers
      if (key.name === "escape" || key.name === "q") {
        onClose();
      } else if (key.name === "up" || key.name === "k") {
        setSelectedIndex((i) => Math.max(0, i - 1));
      } else if (key.name === "down" || key.name === "j") {
        setSelectedIndex((i) => Math.min(schedules.length - 1, i + 1));
      } else if (key.name === "space") {
        handleToggle();
      } else if (key.name === "return") {
        handleViewResult();
      } else if (key.name === "e") {
        const task = schedules[selectedIndex];
        if (task) {
          setEditMode(true);
          setEditName(task.name);
          setEditNameCursorPos(task.name.length);
          setEditText(task.description);
          setCursorPos(task.description.length);
          setEditNotifiers(task.notifiers.filter((n) => availableNotifiers.includes(n)));
          setEditNotifierCursor(0);
          setEditFocus("name");
        }
      } else if (key.name === "d") {
        if (schedules.length > 0) setConfirmDelete(true);
      } else if (key.name === "w") {
        handleToggleWritable();
      } else if (key.name === "x") {
        handleRun();
      } else if (key.name === "r") {
        setLoading(true);
        loadSchedules();
      }
    },
    [
      onClose,
      schedules,
      selectedIndex,
      handleToggle,
      handleToggleWritable,
      confirmDelete,
      handleDelete,
      loadSchedules,
      handleViewResult,
      handleRun,
      editMode,
      editFocus,
      editNotifierCursor,
      availableNotifiers,
      handleSave,
      setSelectedIndex,
      setConfirmDelete,
      setEditMode,
      setEditName,
      setEditNameCursorPos,
      setEditText,
      setCursorPos,
      setEditFocus,
      setEditNotifiers,
      setEditNotifierCursor,
      setLoading,
      nameInput,
      textInput,
    ]
  );

  useKeypress(handleKeypress, { isActive: !viewingResult });

  if (loading) {
    return (
      <Panel title="SCHEDULES" width={contentWidth}>
        <Loading message="Loading schedules..." />
      </Panel>
    );
  }

  if (error) {
    return (
      <Panel title="SCHEDULES" width={contentWidth}>
        <Text color={colors.status.error}>{error}</Text>
        <Footer>q: close</Footer>
      </Panel>
    );
  }

  if (viewingResult) {
    return (
      <ResultViewer
        description={viewingResult.description}
        result={viewingResult.result}
        contentWidth={contentWidth}
        onClose={() => setViewingResult(null)}
      />
    );
  }

  if (editMode) {
    return (
      <ScheduleEditView
        editName={editName}
        editNameCursorPos={editNameCursorPos}
        editText={editText}
        cursorPos={cursorPos}
        setEditText={setEditText}
        setCursorPos={setCursorPos}
        saving={saving}
        contentWidth={contentWidth}
        editFocus={editFocus}
        availableNotifiers={availableNotifiers}
        editNotifiers={editNotifiers}
        editNotifierCursor={editNotifierCursor}
      />
    );
  }

  return (
    <Panel title="SCHEDULES" width={contentWidth}>
      <BaseSelectionList
        items={schedules}
        selectedIndex={selectedIndex}
        renderItem={(item, context) => <ScheduleItem item={item} context={context} textWidth={textWidth} />}
        visibleLines={VISIBLE_LINES}
        emptyMessage="No scheduled tasks. Use chat to create one."
        getKey={(item) => item.task_id}
        width={contentWidth}
        indicator="▶"
      />

      {confirmDelete && schedules[selectedIndex] && (
        <Box marginTop={1}>
          <Text color={colors.status.warning}>
            Delete "{schedules[selectedIndex].description}"? (y/n)
          </Text>
        </Box>
      )}

      <Footer>
        {confirmDelete
          ? "y: confirm  n: cancel"
          : "enter: view  space: toggle  e: edit  w: writable  x: run  d: delete  r: refresh  q: close"}
      </Footer>
    </Panel>
  );
}
