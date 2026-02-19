import React, { useState, useCallback, useRef } from "react";
import type { InputRenderable, TextareaRenderable } from "@opentui/core";
import type { Config } from "../../../types.js";
import { useKeypress, type Key } from "../../../hooks/index.js";
import { Dialog, Loading, colors, BaseSelectionList, Hints } from "../../ui/index.js";
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
  const {
    schedules,
    selectedIndex,
    loading,
    error,
    confirmDelete,
    viewingResult,
    editMode,
    editName,
    editText,
    saving,
    setSelectedIndex,
    setConfirmDelete,
    setViewingResult,
    setEditMode,
    setEditName,
    setEditText,
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

  const [detailScroll, setDetailScroll] = useState(0);

  const nameRef = useRef<InputRenderable | null>(null);
  const descRef = useRef<TextareaRenderable | null>(null);

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

      // Edit mode
      if (editMode) {
        if (key.ctrl && key.name === "s") {
          handleSave(
            nameRef.current?.value,
            descRef.current?.plainText,
          );
          return;
        }
        if (key.name === "escape") {
          setEditMode(false);
          setEditName("");
          setEditText("");
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
            const notifier = availableNotifiers[editNotifierCursor];
            if (notifier) {
              setEditNotifiers((prev) =>
                prev.includes(notifier.name) ? prev.filter((n) => n !== notifier.name) : [...prev, notifier.name]
              );
            }
          }
        }

        // name/description: native input/textarea handles text editing
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
          setEditText(task.description);
          const notifierNames = availableNotifiers.map((n) => n.name);
          setEditNotifiers(task.notifiers.filter((n) => notifierNames.includes(n)));
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
      onClose, schedules, selectedIndex, handleToggle, handleToggleWritable,
      confirmDelete, handleDelete, loadSchedules, handleViewResult, handleRun,
      editMode, editFocus, editNotifierCursor, availableNotifiers, handleSave,
      viewingResult,
      setSelectedIndex, setConfirmDelete, setViewingResult, setEditMode, setEditName,
      setEditText, setEditFocus, setEditNotifiers, setEditNotifierCursor,
      setLoading,
    ]
  );

  useKeypress(handleKeypress, { isActive: true });

  const getFooter = (): React.ReactNode => {
    if (viewingResult) return <Hints items={[["j/k", "scroll"], ["q", "back"]]} />;
    if (editMode) return saving
      ? <text><span fg={colors.text.muted}>Saving...</span></text>
      : <Hints items={[["^S", "save"], ["esc", "cancel"], ["tab", "next"]]} />;
    if (confirmDelete) return <Hints items={[["y", "confirm"], ["n", "cancel"]]} />;
    return <Hints items={[["enter", "detail"], ["spc", "toggle"], ["e", "edit"], ["x", "run"], ["d", "del"]]} />;
  };

  if (loading) {
    return (
      <Dialog title="SCHEDULES" size="large" onClose={onClose}>
        {() => <Loading message="Loading schedules..." />}
      </Dialog>
    );
  }

  if (error) {
    return (
      <Dialog title="SCHEDULES" size="large" onClose={onClose}>
        {() => <text><span fg={colors.status.error}>{error}</span></text>}
      </Dialog>
    );
  }

  return (
    <Dialog
      title="SCHEDULES"
      size="large"
      onClose={onClose}
      footer={getFooter()}
    >
      {({ width, height }) => {
        if (viewingResult) {
          return (
            <ResultViewer
              schedule={viewingResult}
              scroll={detailScroll}
              setScroll={setDetailScroll}
              width={width}
              height={height}
            />
          );
        }

        if (editMode) {
          return (
            <ScheduleEditView
              editName={editName}
              editText={editText}
              saving={saving}
              width={width}
              editFocus={editFocus}
              availableNotifiers={availableNotifiers}
              editNotifiers={editNotifiers}
              editNotifierCursor={editNotifierCursor}
              nameRef={(r) => { nameRef.current = r; }}
              descRef={(r) => { descRef.current = r; }}
            />
          );
        }

        const visibleLines = Math.max(1, Math.floor((height - 2) / 4));

        return (
          <box flexDirection="column" height={height} overflow="hidden">
            <BaseSelectionList
              items={schedules}
              selectedIndex={selectedIndex}
              renderItem={(item, context) => <ScheduleItem item={item} context={context} textWidth={width - 2} />}
              visibleLines={visibleLines}
              emptyMessage="No scheduled tasks. Use chat to create one."
              getKey={(item) => item.task_id}
              width={width}
              indicator="▶"
              showScrollArrows
              showCount
            />

            {confirmDelete && schedules[selectedIndex] && (
              <box marginTop={1}>
                <text>
                  <span fg={colors.status.warning}>
                    Delete "{schedules[selectedIndex].description}"? (y/n)
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
