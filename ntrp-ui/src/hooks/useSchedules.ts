import { useState, useEffect, useRef, useCallback } from "react";
import type { Config } from "../types.js";
import {
  getSchedules,
  getScheduleDetail,
  toggleSchedule,
  updateSchedule,
  deleteSchedule,
  runSchedule,
  toggleWritable,
  getNotifiers,
  setScheduleNotifiers,
  type Schedule,
} from "../api/client.js";

export interface UseSchedulesResult {
  schedules: Schedule[];
  selectedIndex: number;
  loading: boolean;
  error: string | null;
  confirmDelete: boolean;
  viewingResult: { description: string; result: string } | null;
  editMode: boolean;
  editText: string;
  cursorPos: number;
  saving: boolean;
  availableNotifiers: string[];
  setSelectedIndex: React.Dispatch<React.SetStateAction<number>>;
  setConfirmDelete: React.Dispatch<React.SetStateAction<boolean>>;
  setViewingResult: React.Dispatch<React.SetStateAction<{ description: string; result: string } | null>>;
  setEditMode: React.Dispatch<React.SetStateAction<boolean>>;
  setEditText: React.Dispatch<React.SetStateAction<string>>;
  setCursorPos: React.Dispatch<React.SetStateAction<number>>;
  setSaving: React.Dispatch<React.SetStateAction<boolean>>;
  setSchedules: React.Dispatch<React.SetStateAction<Schedule[]>>;
  setLoading: React.Dispatch<React.SetStateAction<boolean>>;
  loadSchedules: () => Promise<void>;
  handleToggle: () => Promise<void>;
  handleDelete: () => Promise<void>;
  handleToggleWritable: () => Promise<void>;
  handleRun: () => Promise<void>;
  handleViewResult: () => Promise<void>;
  handleSave: () => Promise<void>;
  handleToggleNotifier: () => Promise<void>;
}

export function useSchedules(config: Config): UseSchedulesResult {
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [viewingResult, setViewingResult] = useState<{ description: string; result: string } | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [editText, setEditText] = useState("");
  const [cursorPos, setCursorPos] = useState(0);
  const [saving, setSaving] = useState(false);
  const [availableNotifiers, setAvailableNotifiers] = useState<string[]>([]);

  const loadedRef = useRef(false);

  const loadSchedules = useCallback(async () => {
    try {
      const [data, notifiersData] = await Promise.all([
        getSchedules(config),
        getNotifiers(config),
      ]);
      setSchedules(data.schedules);
      setAvailableNotifiers(notifiersData.notifiers);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load schedules");
    } finally {
      setLoading(false);
    }
  }, [config]);

  useEffect(() => {
    if (!loadedRef.current) {
      loadedRef.current = true;
      loadSchedules();
    }
  }, [loadSchedules]);

  const handleToggle = useCallback(async () => {
    const task = schedules[selectedIndex];
    if (!task) return;
    try {
      const result = await toggleSchedule(config, task.task_id);
      setSchedules((prev) =>
        prev.map((s) => (s.task_id === task.task_id ? { ...s, enabled: result.enabled } : s))
      );
    } catch {
      loadSchedules();
    }
  }, [config, schedules, selectedIndex, loadSchedules]);

  const handleDelete = useCallback(async () => {
    const task = schedules[selectedIndex];
    if (!task) return;
    try {
      await deleteSchedule(config, task.task_id);
      setSchedules((prev) => prev.filter((s) => s.task_id !== task.task_id));
      setSelectedIndex((i) => Math.min(i, Math.max(0, schedules.length - 2)));
      setConfirmDelete(false);
    } catch {
      loadSchedules();
      setConfirmDelete(false);
    }
  }, [config, schedules, selectedIndex, loadSchedules]);

  const handleToggleWritable = useCallback(async () => {
    const task = schedules[selectedIndex];
    if (!task) return;
    try {
      const result = await toggleWritable(config, task.task_id);
      setSchedules((prev) =>
        prev.map((s) => (s.task_id === task.task_id ? { ...s, writable: result.writable } : s))
      );
    } catch {
      loadSchedules();
    }
  }, [config, schedules, selectedIndex, loadSchedules]);

  const handleRun = useCallback(async () => {
    const task = schedules[selectedIndex];
    if (!task || task.running_since) return;
    try {
      await runSchedule(config, task.task_id);
      setSchedules((prev) =>
        prev.map((s) =>
          s.task_id === task.task_id ? { ...s, running_since: new Date().toISOString() } : s
        )
      );
    } catch {
      // ignore
    }
  }, [config, schedules, selectedIndex]);

  const handleViewResult = useCallback(async () => {
    const task = schedules[selectedIndex];
    if (!task) return;
    try {
      const detail = await getScheduleDetail(config, task.task_id);
      if (detail.last_result) {
        setViewingResult({ description: detail.description, result: detail.last_result });
      }
    } catch {
      // ignore
    }
  }, [config, schedules, selectedIndex]);

  const handleSave = useCallback(async () => {
    const task = schedules[selectedIndex];
    if (!task) return;
    setSaving(true);
    try {
      await updateSchedule(config, task.task_id, editText);
      setSchedules((prev) =>
        prev.map((s) => (s.task_id === task.task_id ? { ...s, description: editText } : s))
      );
      setEditMode(false);
      setEditText("");
      setCursorPos(0);
    } catch {
      loadSchedules();
    } finally {
      setSaving(false);
    }
  }, [config, schedules, selectedIndex, editText, loadSchedules]);

  const handleToggleNotifier = useCallback(async () => {
    const task = schedules[selectedIndex];
    if (!task || availableNotifiers.length === 0) return;

    let newNotifiers: string[];
    if (availableNotifiers.length === 1) {
      // Single notifier: toggle on/off
      const channel = availableNotifiers[0];
      newNotifiers = task.notifiers.includes(channel)
        ? task.notifiers.filter((n) => n !== channel)
        : [...task.notifiers, channel];
    } else {
      // Multiple notifiers: cycle through — toggle the next one not yet enabled,
      // or if all are enabled, clear them all
      const nextOff = availableNotifiers.find((n) => !task.notifiers.includes(n));
      if (nextOff) {
        newNotifiers = [...task.notifiers, nextOff];
      } else {
        newNotifiers = [];
      }
    }

    // Optimistic update
    setSchedules((prev) =>
      prev.map((s) => (s.task_id === task.task_id ? { ...s, notifiers: newNotifiers } : s))
    );
    try {
      await setScheduleNotifiers(config, task.task_id, newNotifiers);
    } catch {
      loadSchedules();
    }
  }, [config, schedules, selectedIndex, availableNotifiers, loadSchedules]);

  return {
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
    availableNotifiers,
    setSelectedIndex,
    setConfirmDelete,
    setViewingResult,
    setEditMode,
    setEditText,
    setCursorPos,
    setSaving,
    setSchedules,
    setLoading,
    loadSchedules,
    handleToggle,
    handleDelete,
    handleToggleWritable,
    handleRun,
    handleViewResult,
    handleSave,
    handleToggleNotifier,
  };
}
