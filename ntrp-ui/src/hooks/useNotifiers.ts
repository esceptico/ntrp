import { useState, useEffect, useCallback } from "react";
import type { Config } from "../types.js";
import type { Key } from "./useKeypress.js";
import {
  getNotifierConfigs,
  getNotifierTypes,
  deleteNotifierConfig,
  testNotifier,
  type NotifierConfigData,
  type NotifierTypeInfo,
} from "../api/client.js";
import {
  useNotifierForm,
  emptyForm,
  type FormFields,
} from "./useNotifierForm.js";

export type NotifierMode = "list" | "add-type" | "add-form" | "edit-form" | "confirm-delete";

const TYPE_ORDER = ["email", "telegram", "bash"] as const;
const TYPE_LABELS: Record<string, string> = {
  email: "Email",
  telegram: "Telegram",
  bash: "Bash",
};
const TYPE_DESCRIPTIONS: Record<string, string> = {
  email: "Send via connected Gmail",
  telegram: "Send via Telegram bot",
  bash: "Run shell command",
};

export interface UseNotifiersResult {
  configs: NotifierConfigData[];
  types: Record<string, NotifierTypeInfo>;
  selectedIndex: number;
  mode: NotifierMode;
  form: FormFields;
  formType: string;
  activeField: number;
  error: string | null;
  typeSelectIndex: number;
  loading: boolean;
  testing: boolean;
  testResult: { name: string; ok: boolean; error?: string } | null;
  handleKeypress: (key: Key) => void;
}

export function useNotifiers(config: Config): UseNotifiersResult {
  const [configs, setConfigs] = useState<NotifierConfigData[]>([]);
  const [types, setTypes] = useState<Record<string, NotifierTypeInfo>>({});
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [mode, setMode] = useState<NotifierMode>("list");
  const [typeSelectIndex, setTypeSelectIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ name: string; ok: boolean; error?: string } | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [cfgData, typeData] = await Promise.all([
        getNotifierConfigs(config),
        getNotifierTypes(config),
      ]);
      setConfigs(cfgData.configs);
      setTypes(typeData.types);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [config]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const formHook = useNotifierForm({
    config,
    types,
    mode,
    onSaved: loadData,
    onModeChange: setMode,
  });

  const handleDelete = useCallback(async () => {
    const cfg = configs[selectedIndex];
    if (!cfg) return;
    try {
      await deleteNotifierConfig(config, cfg.name);
      await loadData();
      setSelectedIndex((i) => Math.min(i, Math.max(0, configs.length - 2)));
      setMode("list");
    } catch (e) {
      formHook.setError(e instanceof Error ? e.message : "Failed to delete");
      setMode("list");
    }
  }, [config, configs, selectedIndex, loadData, formHook]);

  const handleTest = useCallback(async () => {
    const cfg = configs[selectedIndex];
    if (!cfg || testing) return;
    setTesting(true);
    setTestResult(null);
    try {
      await testNotifier(config, cfg.name);
      setTestResult({ name: cfg.name, ok: true });
    } catch (e) {
      setTestResult({ name: cfg.name, ok: false, error: e instanceof Error ? e.message : "Failed" });
    } finally {
      setTesting(false);
    }
  }, [config, configs, selectedIndex, testing]);

  const handleKeypress = useCallback(
    (key: Key) => {
      if (formHook.saving) return;

      if (mode === "list") {
        if (key.name === "j" || key.name === "down") {
          setSelectedIndex((i) => Math.min(configs.length - 1, i + 1));
        } else if (key.name === "k" || key.name === "up") {
          setSelectedIndex((i) => Math.max(0, i - 1));
        } else if (key.sequence === "a") {
          setTypeSelectIndex(0);
          setMode("add-type");
          formHook.setError(null);
        } else if (key.sequence === "e" && configs.length > 0) {
          const cfg = configs[selectedIndex];
          if (!cfg) return;
          const accounts = types[cfg.type]?.accounts;
          formHook.initForm(cfg.type, {
            name: cfg.name, nameCursor: cfg.name.length,
            fromAccount: cfg.config.from_account || (accounts?.[0] ?? ""),
            toAddress: cfg.config.to_address || "", toAddressCursor: (cfg.config.to_address || "").length,
            userId: cfg.config.user_id || "", userIdCursor: (cfg.config.user_id || "").length,
            command: cfg.config.command || "", commandCursor: (cfg.config.command || "").length,
          }, cfg.name);
          setMode("edit-form");
        } else if (key.sequence === "t" && configs.length > 0) {
          handleTest();
        } else if (key.sequence === "d" && configs.length > 0) {
          setMode("confirm-delete");
        }
        return;
      }

      if (mode === "add-type") {
        if (key.name === "escape") { setMode("list"); }
        else if (key.name === "j" || key.name === "down") { setTypeSelectIndex((i) => Math.min(TYPE_ORDER.length - 1, i + 1)); }
        else if (key.name === "k" || key.name === "up") { setTypeSelectIndex((i) => Math.max(0, i - 1)); }
        else if (key.name === "return") {
          const type = TYPE_ORDER[typeSelectIndex];
          const accounts = types[type]?.accounts;
          formHook.initForm(type, { ...emptyForm(), fromAccount: accounts?.[0] ?? "" }, "");
          setMode("add-form");
        }
        return;
      }

      if (mode === "confirm-delete") {
        if (key.sequence === "y") { handleDelete(); }
        else if (key.sequence === "n" || key.name === "escape") { setMode("list"); }
        return;
      }

      // add-form / edit-form
      formHook.handleFormKey(key);
    },
    [
      mode, configs, selectedIndex, types, typeSelectIndex,
      formHook, handleDelete, handleTest,
    ]
  );

  return {
    configs, types, selectedIndex, mode,
    form: formHook.form, formType: formHook.formType, activeField: formHook.activeField,
    error: formHook.error, typeSelectIndex, loading, testing, testResult, handleKeypress,
  };
}

export { TYPE_ORDER, TYPE_LABELS, TYPE_DESCRIPTIONS };
export type { FormFields } from "./useNotifierForm.js";
