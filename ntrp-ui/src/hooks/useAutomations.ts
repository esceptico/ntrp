import { useState, useEffect, useRef, useCallback, useMemo } from "react";
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
  createAutomation,
  type Automation,
  type NotifierSummary,
  type CreateAutomationData,
  type UpdateAutomationData,
} from "../api/client.js";

export type AutomationTab = "user" | "internal";

interface UseAutomationsResult {
  automations: Automation[];
  activeTab: AutomationTab;
  setActiveTab: React.Dispatch<React.SetStateAction<AutomationTab>>;
  selectedIndex: number;
  loading: boolean;
  error: string | null;
  confirmDelete: boolean;
  viewingResult: Automation | null;
  saving: boolean;
  availableNotifiers: NotifierSummary[];
  availableModels: string[];
  createMode: boolean;
  createError: string | null;
  setSelectedIndex: React.Dispatch<React.SetStateAction<number>>;
  setConfirmDelete: React.Dispatch<React.SetStateAction<boolean>>;
  setViewingResult: React.Dispatch<React.SetStateAction<Automation | null>>;
  setAutomations: React.Dispatch<React.SetStateAction<Automation[]>>;
  setLoading: React.Dispatch<React.SetStateAction<boolean>>;
  setCreateMode: React.Dispatch<React.SetStateAction<boolean>>;
  setCreateError: React.Dispatch<React.SetStateAction<string | null>>;
  loadAutomations: () => Promise<void>;
  handleToggle: () => Promise<void>;
  handleDelete: () => Promise<void>;
  handleToggleWritable: () => Promise<void>;
  handleRun: () => Promise<void>;
  handleViewResult: () => Promise<void>;
  handleCreate: (data: CreateAutomationData) => Promise<void>;
  handleUpdate: (taskId: string, data: UpdateAutomationData) => Promise<void>;
}

export function useAutomations(config: Config): UseAutomationsResult {
  const [allAutomations, setAllAutomations] = useState<Automation[]>([]);
  const [activeTab, setActiveTabRaw] = useState<AutomationTab>("user");
  const setActiveTab = useCallback((v: AutomationTab | ((prev: AutomationTab) => AutomationTab)) => {
    setActiveTabRaw(v);
    setSelectedIndex(0);
  }, []);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [viewingResult, setViewingResult] = useState<Automation | null>(null);
  const [saving, setSaving] = useState(false);
  const [availableNotifiers, setAvailableNotifiers] = useState<NotifierSummary[]>([]);
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [createMode, setCreateMode] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const automations = useMemo(() =>
    allAutomations.filter(a => activeTab === "internal" ? a.builtin : !a.builtin),
    [allAutomations, activeTab],
  );
  const setAutomations = setAllAutomations;

  const loadedRef = useRef(false);

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
    automations, activeTab, setActiveTab,
    selectedIndex, loading, error, confirmDelete, viewingResult,
    saving, availableNotifiers, availableModels,
    createMode, createError,
    setSelectedIndex, setConfirmDelete, setViewingResult,
    setAutomations, setLoading,
    setCreateMode, setCreateError,
    loadAutomations, handleToggle, handleDelete, handleToggleWritable,
    handleRun, handleViewResult, handleCreate, handleUpdate,
  };
}
