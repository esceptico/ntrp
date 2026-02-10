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

export type EditFocus = "name" | "description" | "notifiers";

export interface UseSchedulesResult {
  schedules: Schedule[];
  selectedIndex: number;
  loading: boolean;
  error: string | null;
  confirmDelete: boolean;
  viewingResult: { description: string; result: string } | null;
  editMode: boolean;
  editName: string;
  editNameCursorPos: number;
  editText: string;
  cursorPos: number;
  saving: boolean;
  availableNotifiers: string[];
  editFocus: EditFocus;
  editNotifiers: string[];
  editNotifierCursor: number;
  setSelectedIndex: React.Dispatch<React.SetStateAction<number>>;
  setConfirmDelete: React.Dispatch<React.SetStateAction<boolean>>;
  setViewingResult: React.Dispatch<React.SetStateAction<{ description: string; result: string } | null>>;
  setEditMode: React.Dispatch<React.SetStateAction<boolean>>;
  setEditName: React.Dispatch<React.SetStateAction<string>>;
  setEditNameCursorPos: React.Dispatch<React.SetStateAction<number>>;
  setEditText: React.Dispatch<React.SetStateAction<string>>;
  setCursorPos: React.Dispatch<React.SetStateAction<number>>;
  setSaving: React.Dispatch<React.SetStateAction<boolean>>;
  setSchedules: React.Dispatch<React.SetStateAction<Schedule[]>>;
  setLoading: React.Dispatch<React.SetStateAction<boolean>>;
  setEditFocus: React.Dispatch<React.SetStateAction<EditFocus>>;
  setEditNotifiers: React.Dispatch<React.SetStateAction<string[]>>;
  setEditNotifierCursor: React.Dispatch<React.SetStateAction<number>>;
  loadSchedules: () => Promise<void>;
  handleToggle: () => Promise<void>;
  handleDelete: () => Promise<void>;
  handleToggleWritable: () => Promise<void>;
  handleRun: () => Promise<void>;
  handleViewResult: () => Promise<void>;
  handleSave: () => Promise<void>;
}

export function useSchedules(config: Config): UseSchedulesResult {
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [viewingResult, setViewingResult] = useState<{ description: string; result: string } | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [editName, setEditName] = useState("");
  const [editNameCursorPos, setEditNameCursorPos] = useState(0);
  const [editText, setEditText] = useState("");
  const [cursorPos, setCursorPos] = useState(0);
  const [saving, setSaving] = useState(false);
  const [availableNotifiers, setAvailableNotifiers] = useState<string[]>([]);
  const [editFocus, setEditFocus] = useState<EditFocus>("name");
  const [editNotifiers, setEditNotifiers] = useState<string[]>([]);
  const [editNotifierCursor, setEditNotifierCursor] = useState(0);

  const loadedRef = useRef(false);
  const editNameRef = useRef(editName);
  editNameRef.current = editName;
  const editTextRef = useRef(editText);
  editTextRef.current = editText;
  const editNotifiersRef = useRef(editNotifiers);
  editNotifiersRef.current = editNotifiers;

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
    const name = editNameRef.current;
    const text = editTextRef.current;
    const notifiers = editNotifiersRef.current;
    setSaving(true);
    try {
      await Promise.all([
        updateSchedule(config, task.task_id, { name, description: text }),
        setScheduleNotifiers(config, task.task_id, notifiers),
      ]);
      setSchedules((prev) =>
        prev.map((s) => (s.task_id === task.task_id ? { ...s, name, description: text, notifiers } : s))
      );
      setEditMode(false);
      setEditName("");
      setEditNameCursorPos(0);
      setEditText("");
      setCursorPos(0);
      setEditFocus("name");
    } catch {
      loadSchedules();
    } finally {
      setSaving(false);
    }
  }, [config, schedules, selectedIndex, loadSchedules]);

  return {
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
    availableNotifiers,
    editFocus,
    editNotifiers,
    editNotifierCursor,
    setSelectedIndex,
    setConfirmDelete,
    setViewingResult,
    setEditMode,
    setEditName,
    setEditNameCursorPos,
    setEditText,
    setCursorPos,
    setSaving,
    setSchedules,
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
  };
}
