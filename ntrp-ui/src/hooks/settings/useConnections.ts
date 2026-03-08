import { useCallback, useEffect, useState } from "react";
import type { Config } from "../../types.js";
import type { ServerConfig, GoogleAccount } from "../../api/client.js";
import {
  getGoogleAccounts,
  addGoogleAccount,
  removeGoogleAccount,
  updateConfig,
  updateBrowser,
  getServerConfig,
} from "../../api/client.js";
import type { ConnectionItem } from "../../components/dialogs/settings/config.js";
import { CONNECTION_ITEMS, TOGGLEABLE_SOURCES } from "../../components/dialogs/settings/config.js";
import { useVaultPath, type UseVaultPathResult } from "./useVaultPath.js";
import type { Key } from "../useKeypress.js";

export interface UseConnectionsResult {
  connectionItem: ConnectionItem;
  googleAccounts: GoogleAccount[];
  selectedGoogleIndex: number;
  actionInProgress: string | null;

  vault: UseVaultPathResult;

  showingBrowserDropdown: boolean;
  setShowingBrowserDropdown: React.Dispatch<React.SetStateAction<boolean>>;
  updatingBrowser: boolean;
  browserError: string | null;
  handleSelectBrowser: (browser: string | null) => Promise<void>;

  handleKeypress: (key: Key) => void;
  isEditing: boolean;
  cancelEdit: () => void;
}

export function useConnections(
  config: Config,
  serverConfig: ServerConfig | null,
  onServerConfigChange: (config: ServerConfig) => void,
): UseConnectionsResult {
  const vault = useVaultPath(config, serverConfig, onServerConfigChange);

  const [connectionItem, setConnectionItem] = useState<ConnectionItem>("vault");
  const [googleAccounts, setGoogleAccounts] = useState<GoogleAccount[]>([]);
  const [selectedGoogleIndex, setSelectedGoogleIndex] = useState(0);
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);

  const [showingBrowserDropdown, setShowingBrowserDropdown] = useState(false);
  const [updatingBrowser, setUpdatingBrowser] = useState(false);
  const [browserError, setBrowserError] = useState<string | null>(null);

  useEffect(() => {
    getGoogleAccounts(config)
      .then((result) => setGoogleAccounts(result.accounts))
      .catch(() => {});
  }, [config]);

  const handleAddGoogle = useCallback(async () => {
    if (actionInProgress) return;
    setActionInProgress("Adding account...");
    try {
      await addGoogleAccount(config);
      const accounts = await getGoogleAccounts(config);
      setGoogleAccounts(accounts.accounts);
      const updatedConfig = await getServerConfig(config);
      onServerConfigChange(updatedConfig);
    } catch {
    } finally {
      setActionInProgress(null);
    }
  }, [config, actionInProgress, onServerConfigChange]);

  const handleRemoveGoogle = useCallback(async () => {
    if (actionInProgress || googleAccounts.length === 0) return;
    const account = googleAccounts[selectedGoogleIndex];
    if (!account) return;

    setActionInProgress("Removing...");
    try {
      await removeGoogleAccount(config, account.token_file);
      const accounts = await getGoogleAccounts(config);
      setGoogleAccounts(accounts.accounts);
      setSelectedGoogleIndex(Math.max(0, selectedGoogleIndex - 1));
      const updatedConfig = await getServerConfig(config);
      onServerConfigChange(updatedConfig);
    } catch {
    } finally {
      setActionInProgress(null);
    }
  }, [config, googleAccounts, selectedGoogleIndex, actionInProgress, onServerConfigChange]);

  const handleToggleSource = useCallback(async (source: string) => {
    if (actionInProgress || !serverConfig?.sources) return;
    const current = serverConfig.sources[source]?.enabled ?? false;
    setActionInProgress("Updating...");
    try {
      await updateConfig(config, { sources: { [source]: !current } });
      const updatedConfig = await getServerConfig(config);
      onServerConfigChange(updatedConfig);
    } catch {
    } finally {
      setActionInProgress(null);
    }
  }, [config, serverConfig, actionInProgress, onServerConfigChange]);

  const WEB_MODES = ["auto", "exa", "ddgs", "none"] as const;

  const handleChangeWebSearch = useCallback(async (direction: 1 | -1) => {
    if (!serverConfig) return;
    const current = serverConfig.web_search ?? "auto";
    const idx = WEB_MODES.indexOf(current);
    const next = WEB_MODES[(idx + direction + WEB_MODES.length) % WEB_MODES.length];
    setActionInProgress("Updating...");
    try {
      await updateConfig(config, { web_search: next });
      const updatedConfig = await getServerConfig(config);
      onServerConfigChange(updatedConfig);
    } catch (err) {
      setActionInProgress(err instanceof Error ? err.message : "Failed to update web search");
      await new Promise(r => setTimeout(r, 1500));
    } finally {
      setActionInProgress(null);
    }
  }, [config, serverConfig, onServerConfigChange]);

  const handleSelectBrowser = useCallback(async (browser: string | null) => {
    setShowingBrowserDropdown(false);
    if (browser === serverConfig?.browser) return;
    setBrowserError(null);
    setUpdatingBrowser(true);
    try {
      await updateBrowser(config, browser);
      const updatedConfig = await getServerConfig(config);
      onServerConfigChange(updatedConfig);
    } catch (err) {
      setBrowserError(err instanceof Error ? err.message : "Failed to update browser");
    } finally {
      setUpdatingBrowser(false);
    }
  }, [config, serverConfig?.browser, onServerConfigChange]);

  const isEditing = vault.editingVault;
  const cancelEdit = vault.handleCancelVaultEdit;

  const handleKeypress = useCallback((key: Key) => {
    if (vault.editingVault) {
      if (key.name === "escape") {
        vault.handleCancelVaultEdit();
      } else if (key.name === "return") {
        vault.handleSaveVault();
      } else {
        vault.handleVaultKey(key);
      }
      return;
    }

    const connIdx = CONNECTION_ITEMS.indexOf(connectionItem);
    const isGoogleSource = connectionItem === "google";
    const sourceEnabled = isGoogleSource && serverConfig?.sources?.google?.enabled;
    const hasAccountList = sourceEnabled && googleAccounts.length > 0;

    if (key.name === "up" || key.name === "k") {
      if (hasAccountList && selectedGoogleIndex > 0) {
        setSelectedGoogleIndex(i => i - 1);
      } else if (connIdx > 0) {
        setConnectionItem(CONNECTION_ITEMS[connIdx - 1]);
        setSelectedGoogleIndex(0);
      }
    } else if (key.name === "down" || key.name === "j") {
      if (hasAccountList && selectedGoogleIndex < googleAccounts.length - 1) {
        setSelectedGoogleIndex(i => i + 1);
      } else if (connIdx < CONNECTION_ITEMS.length - 1) {
        setConnectionItem(CONNECTION_ITEMS[connIdx + 1]);
        setSelectedGoogleIndex(0);
      }
    } else if (key.name === "return" || key.name === "space") {
      if (connectionItem === "vault") {
        vault.handleStartVaultEdit();
      } else if (connectionItem === "browser") {
        setShowingBrowserDropdown(true);
      } else if (TOGGLEABLE_SOURCES.includes(connectionItem)) {
        handleToggleSource(connectionItem);
      }
    } else if ((key.name === "right" || key.name === "l") && connectionItem === "web") {
      handleChangeWebSearch(1);
    } else if ((key.name === "left" || key.name === "h") && connectionItem === "web") {
      handleChangeWebSearch(-1);
    } else if (key.sequence === "a" && isGoogleSource && sourceEnabled) {
      handleAddGoogle();
    } else if ((key.sequence === "d" || key.name === "delete") && isGoogleSource && sourceEnabled) {
      handleRemoveGoogle();
    }
  }, [
    connectionItem, serverConfig, googleAccounts, selectedGoogleIndex,
    vault.editingVault, vault.handleCancelVaultEdit, vault.handleSaveVault, vault.handleVaultKey,
    vault.handleStartVaultEdit, handleToggleSource, handleChangeWebSearch, handleAddGoogle, handleRemoveGoogle,
  ]);

  return {
    connectionItem,
    googleAccounts,
    selectedGoogleIndex,
    actionInProgress,
    vault,
    showingBrowserDropdown,
    setShowingBrowserDropdown,
    updatingBrowser,
    browserError,
    handleSelectBrowser,
    handleKeypress,
    isEditing,
    cancelEdit,
  };
}
