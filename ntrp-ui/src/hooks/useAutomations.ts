import { useState, useEffect, useRef, useCallback } from "react";
import type { Config } from "../types.js";
import {
  getAutomations,
  getAutomationDetail,
  getSupportedModels,
  toggleAutomation,
  updateAutomation,
  deleteAutomation,
  runAutomation,
  toggleWritable,
  getNotifiers,
  setAutomationNotifiers,
  createAutomation,
  type Automation,
  type NotifierSummary,
  type CreateAutomationData,
  type UpdateAutomationData,
} from "../api/client.js";

export type EditFocus = "name" | "description" | "notifiers";

interface UseAutomationsResult {
  automations: Automation[];
  selectedIndex: number;
  loading: boolean;
  error: string | null;
  confirmDelete: boolean;
  viewingResult: Automation | null;
  editMode: boolean;
  editName: string;
  editText: string;
  saving: boolean;
  availableNotifiers: NotifierSummary[];
  availableModels: string[];
  editFocus: EditFocus;
  editNotifiers: string[];
  editNotifierCursor: number;
  createMode: boolean;
  createError: string | null;
  setSelectedIndex: React.Dispatch<React.SetStateAction<number>>;
  setConfirmDelete: React.Dispatch<React.SetStateAction<boolean>>;
  setViewingResult: React.Dispatch<React.SetStateAction<Automation | null>>;
  setEditMode: React.Dispatch<React.SetStateAction<boolean>>;
  setEditName: React.Dispatch<React.SetStateAction<string>>;
  setEditText: React.Dispatch<React.SetStateAction<string>>;
  setSaving: React.Dispatch<React.SetStateAction<boolean>>;
  setAutomations: React.Dispatch<React.SetStateAction<Automation[]>>;
  setLoading: React.Dispatch<React.SetStateAction<boolean>>;
  setEditFocus: React.Dispatch<React.SetStateAction<EditFocus>>;
  setEditNotifiers: React.Dispatch<React.SetStateAction<string[]>>;
  setEditNotifierCursor: React.Dispatch<React.SetStateAction<number>>;
  setCreateMode: React.Dispatch<React.SetStateAction<boolean>>;
  setCreateError: React.Dispatch<React.SetStateAction<string | null>>;
  loadAutomations: () => Promise<void>;
  handleToggle: () => Promise<void>;
  handleDelete: () => Promise<void>;
  handleToggleWritable: () => Promise<void>;
  handleRun: () => Promise<void>;
  handleViewResult: () => Promise<void>;
  handleSave: (name?: string, description?: string) => Promise<void>;
  handleCreate: (data: CreateAutomationData) => Promise<void>;
  handleUpdate: (taskId: string, data: UpdateAutomationData) => Promise<void>;
}

export function useAutomations(config: Config): UseAutomationsResult {
  const [automations, setAutomations] = useState<Automation[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [viewingResult, setViewingResult] = useState<Automation | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [editName, setEditName] = useState("");
  const [editText, setEditText] = useState("");
  const [saving, setSaving] = useState(false);
  const [availableNotifiers, setAvailableNotifiers] = useState<NotifierSummary[]>([]);
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [editFocus, setEditFocus] = useState<EditFocus>("name");
  const [editNotifiers, setEditNotifiers] = useState<string[]>([]);
  const [editNotifierCursor, setEditNotifierCursor] = useState(0);
  const [createMode, setCreateMode] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const loadedRef = useRef(false);
  const editNotifiersRef = useRef(editNotifiers);
  editNotifiersRef.current = editNotifiers;

  const loadAutomations = useCallback(async () => {
    try {
      const [data, notifiersData, modelsData] = await Promise.all([
        getAutomations(config),
        getNotifiers(config),
        getSupportedModels(config).catch(() => ({ models: [] as string[] })),
      ]);
      setAutomations(data.automations);
      setAvailableNotifiers(notifiersData.notifiers);
      setAvailableModels(modelsData.models ?? []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load automations");
    } finally {
      setLoading(false);
    }
  }, [config]);

  useEffect(() => {
    if (!loadedRef.current) {
      loadedRef.current = true;
      loadAutomations();
    }
  }, [loadAutomations]);

  const handleToggle = useCallback(async () => {
    const item = automations[selectedIndex];
    if (!item) return;
    try {
      const result = await toggleAutomation(config, item.task_id);
      setAutomations((prev) =>
        prev.map((s) => (s.task_id === item.task_id ? { ...s, enabled: result.enabled } : s))
      );
    } catch {
      loadAutomations();
    }
  }, [config, automations, selectedIndex, loadAutomations]);

  const handleDelete = useCallback(async () => {
    const item = automations[selectedIndex];
    if (!item) return;
    try {
      await deleteAutomation(config, item.task_id);
      setAutomations((prev) => prev.filter((s) => s.task_id !== item.task_id));
      setSelectedIndex((i) => Math.min(i, Math.max(0, automations.length - 2)));
      setConfirmDelete(false);
    } catch {
      loadAutomations();
      setConfirmDelete(false);
    }
  }, [config, automations, selectedIndex, loadAutomations]);

  const handleToggleWritable = useCallback(async () => {
    const item = automations[selectedIndex];
    if (!item) return;
    try {
      const result = await toggleWritable(config, item.task_id);
      setAutomations((prev) =>
        prev.map((s) => (s.task_id === item.task_id ? { ...s, writable: result.writable } : s))
      );
    } catch {
      loadAutomations();
    }
  }, [config, automations, selectedIndex, loadAutomations]);

  const handleRun = useCallback(async () => {
    const item = automations[selectedIndex];
    if (!item || item.running_since) return;
    try {
      await runAutomation(config, item.task_id);
      setAutomations((prev) =>
        prev.map((s) =>
          s.task_id === item.task_id ? { ...s, running_since: new Date().toISOString() } : s
        )
      );
    } catch {
      // ignore
    }
  }, [config, automations, selectedIndex]);

  const handleViewResult = useCallback(async () => {
    const item = automations[selectedIndex];
    if (!item) return;
    try {
      const detail = await getAutomationDetail(config, item.task_id);
      setViewingResult(detail);
    } catch {
      // ignore
    }
  }, [config, automations, selectedIndex]);

  const handleSave = useCallback(async (name?: string, description?: string) => {
    const item = automations[selectedIndex];
    if (!item) return;
    const saveName = name ?? editName;
    const saveText = description ?? editText;
    const notifiers = editNotifiersRef.current;
    setSaving(true);
    try {
      await Promise.all([
        updateAutomation(config, item.task_id, { name: saveName, description: saveText }),
        setAutomationNotifiers(config, item.task_id, notifiers),
      ]);
      setAutomations((prev) =>
        prev.map((s) => (s.task_id === item.task_id ? { ...s, name: saveName, description: saveText, notifiers } : s))
      );
      setEditMode(false);
      setEditName("");
      setEditText("");
      setEditFocus("name");
    } catch {
      loadAutomations();
    } finally {
      setSaving(false);
    }
  }, [config, automations, selectedIndex, editName, editText, loadAutomations]);

  const handleCreate = useCallback(async (data: CreateAutomationData) => {
    setSaving(true);
    setCreateError(null);
    try {
      const automation = await createAutomation(config, data);
      setAutomations((prev) => [...prev, automation]);
      setCreateMode(false);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to create automation";
      setCreateError(msg);
    } finally {
      setSaving(false);
    }
  }, [config]);

  const handleUpdate = useCallback(async (taskId: string, data: UpdateAutomationData) => {
    setSaving(true);
    setCreateError(null);
    try {
      const updated = await updateAutomation(config, taskId, data);
      setAutomations((prev) => prev.map((a) => (a.task_id === taskId ? updated : a)));
      setCreateMode(false);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to update automation";
      setCreateError(msg);
    } finally {
      setSaving(false);
    }
  }, [config]);

  return {
    automations, selectedIndex, loading, error, confirmDelete, viewingResult,
    editMode, editName, editText, saving,
    availableNotifiers, availableModels, editFocus, editNotifiers, editNotifierCursor,
    createMode, createError,
    setSelectedIndex, setConfirmDelete, setViewingResult, setEditMode,
    setEditName, setEditText, setSaving,
    setAutomations, setLoading, setEditFocus, setEditNotifiers, setEditNotifierCursor,
    setCreateMode, setCreateError,
    loadAutomations, handleToggle, handleDelete, handleToggleWritable,
    handleRun, handleViewResult, handleSave, handleCreate, handleUpdate,
  };
}
