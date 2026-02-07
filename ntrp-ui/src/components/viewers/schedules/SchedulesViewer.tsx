import { useCallback } from "react";
import { Box, Text } from "ink";
import type { Config } from "../../../types.js";
import { useKeypress, type Key } from "../../../hooks/useKeypress.js";
import { useDimensions } from "../../../contexts/index.js";
import { Panel, Footer, Loading, colors, BaseSelectionList } from "../../ui/index.js";
import { VISIBLE_LINES } from "../../../lib/constants.js";
import { useSchedules } from "../../../hooks/useSchedules.js";
import { ScheduleItem } from "./ScheduleItem.js";
import { ScheduleEditView } from "./ScheduleEditView.js";
import { ResultViewer } from "./ResultViewer.js";

interface SchedulesViewerProps {
  config: Config;
  onClose: () => void;
}

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
    editText,
    cursorPos,
    saving,
    setSelectedIndex,
    setConfirmDelete,
    setViewingResult,
    setEditMode,
    setEditText,
    setCursorPos,
    setLoading,
    loadSchedules,
    handleToggle,
    handleDelete,
    handleToggleWritable,
    handleRun,
    handleViewResult,
    handleSave,
  } = useSchedules(config);

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
          setEditText("");
          setCursorPos(0);
          return;
        }
        if (key.name === "left") {
          setCursorPos((pos) => Math.max(0, pos - 1));
          return;
        }
        if (key.name === "right") {
          setCursorPos((pos) => Math.min(editText.length, pos + 1));
          return;
        }
        if (key.name === "home") {
          setCursorPos(0);
          return;
        }
        if (key.name === "end") {
          setCursorPos(editText.length);
          return;
        }
        if (key.name === "backspace") {
          if (cursorPos > 0) {
            setEditText((prev) => prev.slice(0, cursorPos - 1) + prev.slice(cursorPos));
            setCursorPos((pos) => pos - 1);
          }
          return;
        }
        if (key.name === "delete") {
          if (cursorPos < editText.length) {
            setEditText((prev) => prev.slice(0, cursorPos) + prev.slice(cursorPos + 1));
          }
          return;
        }
        if (key.insertable && !key.ctrl && !key.meta && key.sequence) {
          const char = key.name === "return" ? "\n" : key.name === "space" ? " " : key.sequence;
          setEditText((prev) => prev.slice(0, cursorPos) + char + prev.slice(cursorPos));
          setCursorPos((pos) => pos + 1);
          return;
        }
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
          setEditText(task.description);
          setCursorPos(task.description.length);
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
      editText,
      cursorPos,
      handleSave,
      setSelectedIndex,
      setConfirmDelete,
      setEditMode,
      setEditText,
      setCursorPos,
      setLoading,
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
        editText={editText}
        cursorPos={cursorPos}
        saving={saving}
        contentWidth={contentWidth}
        textWidth={textWidth}
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
