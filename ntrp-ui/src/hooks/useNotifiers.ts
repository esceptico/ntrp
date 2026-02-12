import { useState, useEffect, useRef, useCallback } from "react";
import type { Config } from "../types.js";
import type { Key } from "./useKeypress.js";
import { useTextInput } from "./useTextInput.js";
import {
  getNotifierConfigs,
  getNotifierTypes,
  createNotifierConfig,
  updateNotifierConfig,
  deleteNotifierConfig,
  testNotifier,
  type NotifierConfigData,
  type NotifierTypeInfo,
} from "../api/client.js";

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

interface FormFields {
  name: string;
  nameCursor: number;
  fromAccount: string;
  toAddress: string;
  toAddressCursor: number;
  userId: string;
  userIdCursor: number;
  command: string;
  commandCursor: number;
}

function emptyForm(): FormFields {
  return {
    name: "", nameCursor: 0,
    fromAccount: "", toAddress: "", toAddressCursor: 0,
    userId: "", userIdCursor: 0,
    command: "", commandCursor: 0,
  };
}

function fieldCountForType(type: string): number {
  if (type === "email") return 3;
  if (type === "telegram") return 2;
  return 2;
}

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
  const [form, setForm] = useState<FormFields>(emptyForm);
  const [formType, setFormType] = useState("email");
  const [activeField, setActiveField] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [typeSelectIndex, setTypeSelectIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ name: string; ok: boolean; error?: string } | null>(null);
  const originalNameRef = useRef("");

  const loadedRef = useRef(false);

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
    if (!loadedRef.current) {
      loadedRef.current = true;
      loadData();
    }
  }, [loadData]);

  const nameInput = useTextInput({
    text: form.name,
    cursorPos: form.nameCursor,
    setText: (v) => setForm((f) => ({ ...f, name: typeof v === "function" ? v(f.name) : v })),
    setCursorPos: (v) => setForm((f) => ({ ...f, nameCursor: typeof v === "function" ? v(f.nameCursor) : v })),
  });

  const toAddressInput = useTextInput({
    text: form.toAddress,
    cursorPos: form.toAddressCursor,
    setText: (v) => setForm((f) => ({ ...f, toAddress: typeof v === "function" ? v(f.toAddress) : v })),
    setCursorPos: (v) => setForm((f) => ({ ...f, toAddressCursor: typeof v === "function" ? v(f.toAddressCursor) : v })),
  });

  const userIdInput = useTextInput({
    text: form.userId,
    cursorPos: form.userIdCursor,
    setText: (v) => setForm((f) => ({ ...f, userId: typeof v === "function" ? v(f.userId) : v })),
    setCursorPos: (v) => setForm((f) => ({ ...f, userIdCursor: typeof v === "function" ? v(f.userIdCursor) : v })),
  });

  const commandInput = useTextInput({
    text: form.command,
    cursorPos: form.commandCursor,
    setText: (v) => setForm((f) => ({ ...f, command: typeof v === "function" ? v(f.command) : v })),
    setCursorPos: (v) => setForm((f) => ({ ...f, commandCursor: typeof v === "function" ? v(f.commandCursor) : v })),
  });

  const getActiveTextInput = useCallback(() => {
    if (formType === "email") {
      if (activeField === 0) return nameInput;
      if (activeField === 2) return toAddressInput;
    } else if (formType === "telegram") {
      if (activeField === 0) return nameInput;
      if (activeField === 1) return userIdInput;
    } else {
      if (activeField === 0) return nameInput;
      if (activeField === 1) return commandInput;
    }
    return null;
  }, [formType, activeField, nameInput, toAddressInput, userIdInput, commandInput]);

  const buildConfig = useCallback((): Record<string, string> => {
    if (formType === "email") return { from_account: form.fromAccount, to_address: form.toAddress };
    if (formType === "telegram") return { user_id: form.userId };
    return { command: form.command };
  }, [formType, form]);

  const handleSave = useCallback(async () => {
    if (saving) return;
    setError(null);
    setSaving(true);

    try {
      const cfg = buildConfig();
      if (mode === "add-form") {
        await createNotifierConfig(config, { name: form.name, type: formType, config: cfg });
      } else {
        await updateNotifierConfig(config, originalNameRef.current, cfg, form.name);
      }
      await loadData();
      setMode("list");
      setForm(emptyForm());
      setActiveField(0);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }, [saving, mode, config, form.name, formType, buildConfig, loadData]);

  const handleDelete = useCallback(async () => {
    const cfg = configs[selectedIndex];
    if (!cfg) return;
    try {
      await deleteNotifierConfig(config, cfg.name);
      await loadData();
      setSelectedIndex((i) => Math.min(i, Math.max(0, configs.length - 2)));
      setMode("list");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete");
      setMode("list");
    }
  }, [config, configs, selectedIndex, loadData]);

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
      if (saving) return;

      if (mode === "list") {
        if (key.name === "j" || key.name === "down") {
          setSelectedIndex((i) => Math.min(configs.length - 1, i + 1));
        } else if (key.name === "k" || key.name === "up") {
          setSelectedIndex((i) => Math.max(0, i - 1));
        } else if (key.sequence === "a") {
          setTypeSelectIndex(0);
          setMode("add-type");
          setError(null);
        } else if (key.sequence === "e" && configs.length > 0) {
          const cfg = configs[selectedIndex];
          if (!cfg) return;
          const accounts = types[cfg.type]?.accounts;
          originalNameRef.current = cfg.name;
          setFormType(cfg.type);
          setForm({
            name: cfg.name, nameCursor: cfg.name.length,
            fromAccount: cfg.config.from_account || (accounts?.[0] ?? ""),
            toAddress: cfg.config.to_address || "", toAddressCursor: (cfg.config.to_address || "").length,
            userId: cfg.config.user_id || "", userIdCursor: (cfg.config.user_id || "").length,
            command: cfg.config.command || "", commandCursor: (cfg.config.command || "").length,
          });
          setActiveField(0);
          setError(null);
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
          setFormType(type);
          setForm({ ...emptyForm(), fromAccount: accounts?.[0] ?? "" });
          setActiveField(0);
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
      if (key.name === "escape") {
        setMode("list");
        setForm(emptyForm());
        setActiveField(0);
        setError(null);
        return;
      }

      if (key.name === "s" && key.ctrl) { handleSave(); return; }

      const fieldCount = fieldCountForType(formType);

      if (key.name === "up" || (key.name === "k" && key.ctrl)) { setActiveField((i) => Math.max(0, i - 1)); return; }
      if (key.name === "down" || (key.name === "j" && key.ctrl)) { setActiveField((i) => Math.min(fieldCount - 1, i + 1)); return; }

      if (key.name === "return") {
        if (activeField < fieldCount - 1) { setActiveField((i) => i + 1); }
        else { handleSave(); }
        return;
      }

      const fromAccountField = 1;
      if (formType === "email" && activeField === fromAccountField) {
        const accounts = types.email?.accounts ?? [];
        if (accounts.length > 0 && (key.name === "tab" || key.name === "left" || key.name === "right")) {
          const idx = accounts.indexOf(form.fromAccount);
          const dir = key.name === "left" ? -1 : 1;
          const next = (idx + dir + accounts.length) % accounts.length;
          setForm((f) => ({ ...f, fromAccount: accounts[next] }));
          return;
        }
      }

      const textInput = getActiveTextInput();
      if (textInput) { textInput.handleKey(key); }
    },
    [
      mode, configs, selectedIndex, types, typeSelectIndex, formType, activeField,
      form.fromAccount, saving, handleSave, handleDelete, handleTest, getActiveTextInput,
    ]
  );

  return {
    configs, types, selectedIndex, mode, form, formType, activeField,
    error, typeSelectIndex, loading, testing, testResult, handleKeypress,
  };
}

export { TYPE_ORDER, TYPE_LABELS, TYPE_DESCRIPTIONS };
