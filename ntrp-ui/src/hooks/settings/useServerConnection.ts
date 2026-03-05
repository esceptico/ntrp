import { useCallback, useState } from "react";
import type { Config } from "../../types.js";
import { checkHealth } from "../../api/client.js";
import { setApiKey as setFetchApiKey } from "../../api/fetch.js";
import { setCredentials } from "../../lib/secrets.js";
import { useTextInput } from "../useTextInput.js";
import type { Key } from "../useKeypress.js";

export interface UseServerConnectionResult {
  serverIndex: number;
  setServerIndex: React.Dispatch<React.SetStateAction<number>>;
  editingServer: boolean;
  serverUrl: string;
  serverUrlCursor: number;
  serverApiKey: string;
  serverApiKeyCursor: number;
  serverSaving: boolean;
  serverError: string | null;
  setServerUrlCursor: React.Dispatch<React.SetStateAction<number>>;
  setServerApiKeyCursor: React.Dispatch<React.SetStateAction<number>>;
  setEditingServer: React.Dispatch<React.SetStateAction<boolean>>;
  handleSaveServer: () => Promise<void>;
  handleCancelServerEdit: () => void;
  handleServerUrlKey: (key: Key) => boolean;
  handleServerApiKeyKey: (key: Key) => boolean;
}

export function useServerConnection(
  config: Config,
  onServerCredentialsChange: (config: Config) => void,
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
      const health = await checkHealth({ serverUrl: url, apiKey: key, needsSetup: false });
      if (!health.ok) {
        setServerError("Could not connect to server");
        setServerSaving(false);
        return;
      }
      await setCredentials(url, key);
      onServerCredentialsChange({ serverUrl: url, apiKey: key, needsSetup: false });
      setEditingServer(false);
    } catch {
      setServerError("Could not connect to server");
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

  return {
    serverIndex,
    setServerIndex,
    editingServer,
    serverUrl,
    serverUrlCursor,
    serverApiKey,
    serverApiKeyCursor,
    serverSaving,
    serverError,
    setServerUrlCursor,
    setServerApiKeyCursor,
    setEditingServer,
    handleSaveServer,
    handleCancelServerEdit,
    handleServerUrlKey,
    handleServerApiKeyKey,
  };
}
