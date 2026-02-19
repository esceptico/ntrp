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
  type NotifierSummary,
} from "../api/client.js";

export type EditFocus = "name" | "description" | "notifiers";

interface UseSchedulesResult {
  schedules: Schedule[];
  selectedIndex: number;
  loading: boolean;
  error: string | null;
  confirmDelete: boolean;
  viewingResult: Schedule | null;
  editMode: boolean;
  editName: string;
  editText: string;
  saving: boolean;
  availableNotifiers: NotifierSummary[];
  editFocus: EditFocus;
  editNotifiers: string[];
  editNotifierCursor: number;
  setSelectedIndex: React.Dispatch<React.SetStateAction<number>>;
  setConfirmDelete: React.Dispatch<React.SetStateAction<boolean>>;
  setViewingResult: React.Dispatch<React.SetStateAction<Schedule | null>>;
  setEditMode: React.Dispatch<React.SetStateAction<boolean>>;
  setEditName: React.Dispatch<React.SetStateAction<string>>;
  setEditText: React.Dispatch<React.SetStateAction<string>>;
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
  handleSave: (name?: string, description?: string) => Promise<void>;
}

export function useSchedules(config: Config): UseSchedulesResult {
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [viewingResult, setViewingResult] = useState<Schedule | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [editName, setEditName] = useState("");
  const [editText, setEditText] = useState("");
  const [saving, setSaving] = useState(false);
  const [availableNotifiers, setAvailableNotifiers] = useState<NotifierSummary[]>([]);
  const [editFocus, setEditFocus] = useState<EditFocus>("name");
  const [editNotifiers, setEditNotifiers] = useState<string[]>([]);
  const [editNotifierCursor, setEditNotifierCursor] = useState(0);

  const loadedRef = useRef(false);
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
      setViewingResult(detail);
    } catch {
      // ignore
    }
  }, [config, schedules, selectedIndex]);

  const handleSave = useCallback(async (name?: string, description?: string) => {
    const task = schedules[selectedIndex];
    if (!task) return;
    const saveName = name ?? editName;
    const saveText = description ?? editText;
    const notifiers = editNotifiersRef.current;
    setSaving(true);
    try {
      await Promise.all([
        updateSchedule(config, task.task_id, { name: saveName, description: saveText }),
        setScheduleNotifiers(config, task.task_id, notifiers),
      ]);
      setSchedules((prev) =>
        prev.map((s) => (s.task_id === task.task_id ? { ...s, name: saveName, description: saveText, notifiers } : s))
      );
      setEditMode(false);
      setEditName("");
      setEditText("");
      setEditFocus("name");
    } catch {
      loadSchedules();
    } finally {
      setSaving(false);
    }
  }, [config, schedules, selectedIndex, editName, editText, loadSchedules]);

  return {
    schedules, selectedIndex, loading, error, confirmDelete, viewingResult,
    editMode, editName, editText, saving,
    availableNotifiers, editFocus, editNotifiers, editNotifierCursor,
    setSelectedIndex, setConfirmDelete, setViewingResult, setEditMode,
    setEditName, setEditText, setSaving,
    setSchedules, setLoading, setEditFocus, setEditNotifiers, setEditNotifierCursor,
    loadSchedules, handleToggle, handleDelete, handleToggleWritable,
    handleRun, handleViewResult, handleSave,
  };
}
