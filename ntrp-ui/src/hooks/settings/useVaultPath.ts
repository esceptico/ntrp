import { useCallback, useState } from "react";
import type { Config } from "../../types.js";
import type { ServerConfig } from "../../api/client.js";
import { updateVaultPath, getServerConfig } from "../../api/client.js";
import { useTextInput } from "../useTextInput.js";
import type { Key } from "../useKeypress.js";

export interface UseVaultPathResult {
  editingVault: boolean;
  vaultPath: string;
  vaultCursorPos: number;
  updatingVault: boolean;
  vaultError: string | null;
  handleSaveVault: () => Promise<void>;
  handleCancelVaultEdit: () => void;
  handleStartVaultEdit: () => void;
  handleVaultKey: (key: Key) => boolean;
}

export function useVaultPath(
  config: Config,
  serverConfig: ServerConfig | null,
  onServerConfigChange: (config: ServerConfig) => void,
): UseVaultPathResult {
  const [editingVault, setEditingVault] = useState(false);
  const [vaultPath, setVaultPath] = useState(serverConfig?.vault_path || "");
  const [vaultCursorPos, setVaultCursorPos] = useState(0);
  const [updatingVault, setUpdatingVault] = useState(false);
  const [vaultError, setVaultError] = useState<string | null>(null);

  const { handleKey: handleVaultKey } = useTextInput({
    text: vaultPath,
    cursorPos: vaultCursorPos,
    setText: setVaultPath,
    setCursorPos: setVaultCursorPos,
  });

  const handleSaveVault = useCallback(async () => {
    if (updatingVault) return;
    const trimmed = vaultPath.trim();
    if (!trimmed) {
      setVaultError("Path cannot be empty");
      return;
    }
    setVaultError(null);
    setUpdatingVault(true);
    try {
      await updateVaultPath(config, trimmed);
      const updatedConfig = await getServerConfig(config);
      onServerConfigChange(updatedConfig);
      setEditingVault(false);
    } catch (err) {
      setVaultError(err instanceof Error ? err.message : "Failed to update vault path");
    } finally {
      setUpdatingVault(false);
    }
  }, [config, vaultPath, updatingVault, onServerConfigChange]);

  const handleCancelVaultEdit = useCallback(() => {
    setVaultPath(serverConfig?.vault_path || "");
    setVaultCursorPos(0);
    setVaultError(null);
    setEditingVault(false);
  }, [serverConfig?.vault_path]);

  const handleStartVaultEdit = useCallback(() => {
    const path = serverConfig?.vault_path || "";
    setVaultPath(path);
    setVaultCursorPos(path.length);
    setVaultError(null);
    setEditingVault(true);
  }, [serverConfig?.vault_path]);

  return {
    editingVault,
    vaultPath,
    vaultCursorPos,
    updatingVault,
    vaultError,
    handleSaveVault,
    handleCancelVaultEdit,
    handleStartVaultEdit,
    handleVaultKey,
  };
}
