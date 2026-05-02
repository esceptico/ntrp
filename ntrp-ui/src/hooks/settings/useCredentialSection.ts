import { useCallback, useEffect, useState } from "react";
import { useTextInput } from "../useTextInput.js";
import type { Key } from "../useKeypress.js";
import { handleListNav } from "../keyUtils.js";

export interface CredentialItem {
  id: string;
  connected: boolean;
  from_env?: boolean;
  auth_type?: "api_key" | "oauth";
}

export interface UseCredentialSectionResult<T extends CredentialItem> {
  items: T[];
  selectedIndex: number;
  editing: boolean;
  keyValue: string;
  keyCursor: number;
  saving: boolean;
  error: string | null;
  notice: string | null;
  oauthUrl: string | null;
  oauthPendingId: string | null;
  confirmDisconnect: boolean;
  refresh: () => void;
  handleKeypress: (key: Key) => void;
  isEditing: boolean;
  cancelEdit: () => void;
}

interface Options<T extends CredentialItem> {
  fetchItems: () => Promise<T[]>;
  connect: (id: string, key: string) => Promise<unknown>;
  startOAuth?: (id: string) => Promise<{ url: string; instructions?: string; opened?: boolean }>;
  disconnect: (id: string) => Promise<unknown>;
  canEdit?: (item: T) => boolean;
  canDisconnect?: (item: T) => boolean;
  onEnter?: (item: T) => boolean;
  onChanged?: () => Promise<void> | void;
}

export function useCredentialSection<T extends CredentialItem>({
  fetchItems,
  connect,
  startOAuth,
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
  const [notice, setNotice] = useState<string | null>(null);
  const [oauthUrl, setOauthUrl] = useState<string | null>(null);
  const [oauthPendingId, setOauthPendingId] = useState<string | null>(null);
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

  useEffect(() => {
    if (!oauthPendingId) return;
    const timer = setInterval(() => {
      fetchItems()
        .then((fresh) => {
          setItems(fresh);
          const item = fresh.find((entry) => entry.id === oauthPendingId);
          if (item?.connected) {
            setOauthPendingId(null);
            setOauthUrl(null);
            setNotice("Connected");
            void notifyChanged();
          }
        })
        .catch(() => {});
    }, 1000);
    return () => clearInterval(timer);
  }, [fetchItems, notifyChanged, oauthPendingId]);

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
      setNotice("Connected");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to connect");
    } finally {
      setSaving(false);
    }
  }, [saving, keyValue, items, selectedIndex, connect, refresh, notifyChanged]);

  const handleOAuthStart = useCallback(async () => {
    if (saving || !startOAuth) return;
    const item = items[selectedIndex];
    if (!item) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    setOauthUrl(null);
    try {
      const result = await startOAuth(item.id);
      setOauthPendingId(item.id);
      setOauthUrl(result.url);
      setNotice(result.instructions ?? (result.opened ? "Browser sign-in started" : "Open the sign-in URL"));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start sign-in");
    } finally {
      setSaving(false);
    }
  }, [saving, startOAuth, items, selectedIndex]);

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
      setNotice("Disconnected");
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
      } else if (item?.auth_type === "oauth" && !item.connected && startOAuth) {
        handleOAuthStart();
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
    handleDisconnect, handleSave, handleKeyInput, handleOAuthStart, canEdit, canDisconnect, onEnter, startOAuth,
  ]);

  return {
    items, selectedIndex, editing, keyValue, keyCursor,
    saving, error, notice, oauthUrl, oauthPendingId, confirmDisconnect, refresh,
    handleKeypress, isEditing, cancelEdit,
  };
}
