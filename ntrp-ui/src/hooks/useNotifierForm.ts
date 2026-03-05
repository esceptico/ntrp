import { useState, useRef, useCallback } from "react";
import type { Config } from "../types.js";
import type { Key } from "./useKeypress.js";
import { useTextInput } from "./useTextInput.js";
import {
  createNotifierConfig,
  updateNotifierConfig,
  type NotifierTypeInfo,
} from "../api/client.js";
import type { NotifierMode } from "./useNotifiers.js";

export interface FormFields {
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

export function emptyForm(): FormFields {
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

interface UseNotifierFormOptions {
  config: Config;
  types: Record<string, NotifierTypeInfo>;
  mode: NotifierMode;
  onSaved: () => Promise<void>;
  onModeChange: (mode: NotifierMode) => void;
}

interface UseNotifierFormResult {
  form: FormFields;
  formType: string;
  activeField: number;
  saving: boolean;
  initForm: (type: string, fields: FormFields, originalName: string) => void;
  resetForm: () => void;
  handleSave: () => Promise<void>;
  handleFormKey: (key: Key) => void;
  setError: (error: string | null) => void;
  error: string | null;
}

export function useNotifierForm({
  config,
  types,
  mode,
  onSaved,
  onModeChange,
}: UseNotifierFormOptions): UseNotifierFormResult {
  const [form, setForm] = useState<FormFields>(emptyForm);
  const [formType, setFormType] = useState("email");
  const [activeField, setActiveField] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const originalNameRef = useRef("");

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

  const initForm = useCallback((type: string, fields: FormFields, originalName: string) => {
    setFormType(type);
    setForm(fields);
    setActiveField(0);
    setError(null);
    originalNameRef.current = originalName;
  }, []);

  const resetForm = useCallback(() => {
    setForm(emptyForm());
    setActiveField(0);
    setError(null);
  }, []);

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
      await onSaved();
      onModeChange("list");
      setForm(emptyForm());
      setActiveField(0);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }, [saving, mode, config, form.name, formType, buildConfig, onSaved, onModeChange]);

  const handleFormKey = useCallback((key: Key) => {
    if (key.name === "escape") {
      onModeChange("list");
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
  }, [formType, activeField, form.fromAccount, types, handleSave, getActiveTextInput, onModeChange]);

  return {
    form, formType, activeField, saving, error, setError,
    initForm, resetForm, handleSave, handleFormKey,
  };
}
