import { useCallback, useState } from "react";
import type { Config } from "../../types.js";
import { checkHealth } from "../../api/client.js";
import { setApiKey as setFetchApiKey } from "../../api/fetch.js";
import { setCredentials } from "../../lib/secrets.js";
import { useTextInput } from "../useTextInput.js";
import type { Key } from "../useKeypress.js";
import { handleListNav } from "../keyUtils.js";

export interface UseServerConnectionResult {
  serverIndex: number;
  editingServer: boolean;
  serverUrl: string;
  serverUrlCursor: number;
  serverApiKey: string;
  serverApiKeyCursor: number;
  serverSaving: boolean;
  serverError: string | null;
  streaming: boolean;
  handleKeypress: (key: Key) => void;
  isEditing: boolean;
  cancelEdit: () => void;
}

export function useServerConnection(
  config: Config,
  onServerCredentialsChange: (config: Config) => void,
  streaming: boolean = true,
  onToggleStreaming?: () => void,
): UseServerConnectionResult {
  const [serverIndex, setServerIndex] = useState(0);
  const [editingServer, setEditingServer] = useState(false);
  const [serverUrl, setServerUrl] = useState(config.serverUrl);
  const [serverUrlCursor, setServerUrlCursor] = useState(0);
  const [serverApiKey, setServerApiKey] = useState(config.apiKey);
  const [serverApiKeyCursor, setServerApiKeyCursor] = useState(0);
  const [serverSaving, setServerSaving] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const { handleKey: handleServerUrlKey } = useTextInput({
    text: serverUrl,
    cursorPos: serverUrlCursor,
    setText: setServerUrl,
    setCursorPos: setServerUrlCursor,
  });

  const { handleKey: handleServerApiKeyKey } = useTextInput({
    text: serverApiKey,
    cursorPos: serverApiKeyCursor,
    setText: setServerApiKey,
    setCursorPos: setServerApiKeyCursor,
  });

  const handleSaveServer = useCallback(async () => {
    if (serverSaving) return;
    const url = serverUrl.trim();
    const key = serverApiKey.trim();
    if (!url || !key) {
      setServerError("Both fields are required");
      return;
    }
    setServerError(null);
    setServerSaving(true);
    try {
      setFetchApiKey(key);
      await setCredentials(url, key);
      const health = await checkHealth({ serverUrl: url, apiKey: key, needsSetup: false });
      onServerCredentialsChange({ serverUrl: url, apiKey: key, needsSetup: false });
      setEditingServer(false);
      if (!health.ok) {
        setServerError("Saved. Waiting for server…");
      }
    } catch {
      onServerCredentialsChange({ serverUrl: url, apiKey: key, needsSetup: false });
      setEditingServer(false);
      setServerError("Saved. Waiting for server…");
    } finally {
      setServerSaving(false);
    }
  }, [serverUrl, serverApiKey, serverSaving, onServerCredentialsChange]);

  const handleCancelServerEdit = useCallback(() => {
    setServerUrl(config.serverUrl);
    setServerApiKey(config.apiKey);
    setServerUrlCursor(0);
    setServerApiKeyCursor(0);
    setServerError(null);
    setEditingServer(false);
  }, [config]);

  const isEditing = editingServer;

  const handleKeypress = useCallback((key: Key) => {
    if (editingServer) {
      if (key.name === "s" && key.ctrl) {
        handleSaveServer();
      } else if (key.name === "tab") {
        setServerIndex(i => (i === 0 ? 1 : 0));
      } else if (serverIndex === 0) {
        handleServerUrlKey(key);
      } else {
        handleServerApiKeyKey(key);
      }
    } else {
      if (handleListNav(key, 3, setServerIndex)) {
        // handled
      } else if (key.name === "return" || key.name === "space") {
        if (serverIndex === 2) {
          onToggleStreaming?.();
        } else {
          setServerUrlCursor(serverUrl.length);
          setServerApiKeyCursor(serverApiKey.length);
          setEditingServer(true);
        }
      }
    }
  }, [editingServer, serverIndex, serverUrl, serverApiKey, handleSaveServer, handleServerUrlKey, handleServerApiKeyKey]);

  return {
    serverIndex,
    editingServer,
    serverUrl,
    serverUrlCursor,
    serverApiKey,
    serverApiKeyCursor,
    serverSaving,
    serverError,
    streaming,
    handleKeypress,
    isEditing,
    cancelEdit: handleCancelServerEdit,
  };
}
