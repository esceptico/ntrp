import { useCallback, useState } from "react";
import { useTextInput } from "../useTextInput.js";
import type { Key } from "../useKeypress.js";
import { handleListNav } from "../keyUtils.js";

export interface CredentialItem {
  id: string;
  connected: boolean;
  from_env?: boolean;
}

export interface UseCredentialSectionResult<T extends CredentialItem> {
  items: T[];
  selectedIndex: number;
  editing: boolean;
  keyValue: string;
  keyCursor: number;
  saving: boolean;
  error: string | null;
  confirmDisconnect: boolean;
  refresh: () => void;
  handleKeypress: (key: Key) => void;
  isEditing: boolean;
  cancelEdit: () => void;
}

interface Options<T extends CredentialItem> {
  fetchItems: () => Promise<T[]>;
  connect: (id: string, key: string) => Promise<unknown>;
  disconnect: (id: string) => Promise<unknown>;
  canEdit?: (item: T) => boolean;
  canDisconnect?: (item: T) => boolean;
  onEnter?: (item: T) => boolean;
  onChanged?: () => Promise<void> | void;
}

export function useCredentialSection<T extends CredentialItem>({
  fetchItems,
  connect,
  disconnect,
  canEdit = (item) => !item.from_env,
  canDisconnect = (item) => item.connected && !item.from_env,
  onEnter,
  onChanged,
}: Options<T>): UseCredentialSectionResult<T> {
  const [items, setItems] = useState<T[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [editing, setEditing] = useState(false);
  const [keyValue, setKeyValue] = useState("");
  const [keyCursor, setKeyCursor] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmDisconnect, setConfirmDisconnect] = useState(false);

  const { handleKey: handleKeyInput } = useTextInput({
    text: keyValue, cursorPos: keyCursor,
    setText: setKeyValue, setCursorPos: setKeyCursor,
  });

  const refresh = useCallback(() => {
    fetchItems().then(setItems).catch(() => {});
  }, [fetchItems]);

  const notifyChanged = useCallback(async () => {
    try {
      await onChanged?.();
    } catch {
      // The edit succeeded; stale snapshots will refresh on the next heartbeat.
    }
  }, [onChanged]);

  const handleSave = useCallback(async () => {
    if (saving) return;
    const key = keyValue.trim();
    const item = items[selectedIndex];
    if (!key || !item) return;
    setSaving(true);
    setError(null);
    try {
      await connect(item.id, key);
      refresh();
      await notifyChanged();
      setEditing(false);
      setKeyValue("");
      setKeyCursor(0);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to connect");
    } finally {
      setSaving(false);
    }
  }, [saving, keyValue, items, selectedIndex, connect, refresh, notifyChanged]);

  const handleDisconnect = useCallback(async () => {
    if (saving) return;
    const item = items[selectedIndex];
    if (!item) return;
    setSaving(true);
    setError(null);
    try {
      await disconnect(item.id);
      refresh();
      await notifyChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to disconnect");
    } finally {
      setSaving(false);
      setConfirmDisconnect(false);
    }
  }, [saving, items, selectedIndex, disconnect, refresh, notifyChanged]);

  const isEditing = editing || confirmDisconnect;

  const cancelEdit = useCallback(() => {
    if (editing) {
      setEditing(false);
      setKeyValue("");
      setKeyCursor(0);
      setError(null);
    } else if (confirmDisconnect) {
      setConfirmDisconnect(false);
    }
  }, [editing, confirmDisconnect]);

  const handleKeypress = useCallback((key: Key) => {
    if (confirmDisconnect) {
      if (key.sequence === "y") handleDisconnect();
      else setConfirmDisconnect(false);
      return;
    }
    if (editing) {
      if (key.name === "return") handleSave();
      else handleKeyInput(key);
      return;
    }
    if (handleListNav(key, items.length, setSelectedIndex)) {
      // handled
    } else if (key.name === "return" || key.name === "space") {
      const item = items[selectedIndex];
      if (item && onEnter?.(item)) {
        // handled by custom onEnter
      } else if (item && canEdit(item)) {
        setKeyValue("");
        setKeyCursor(0);
        setError(null);
        setEditing(true);
      }
    } else if (key.sequence === "d") {
      const item = items[selectedIndex];
      if (item && canDisconnect(item)) {
        setConfirmDisconnect(true);
      }
    }
  }, [
    confirmDisconnect, editing, items, selectedIndex,
    handleDisconnect, handleSave, handleKeyInput, canEdit, canDisconnect, onEnter,
  ]);

  return {
    items, selectedIndex, editing, keyValue, keyCursor,
    saving, error, confirmDisconnect, refresh,
    handleKeypress, isEditing, cancelEdit,
  };
}
