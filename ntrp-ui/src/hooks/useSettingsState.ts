import { useCallback, useEffect, useState } from "react";
import type { Config } from "../types.js";
import type { Settings } from "./useSettings.js";
import { useNotifiers, type UseNotifiersResult } from "./useNotifiers.js";
import { useSkills, type UseSkillsResult } from "./useSkills.js";
import {
  getGoogleAccounts,
  addGoogleAccount,
  removeGoogleAccount,
  updateConfig,
  updateBrowser,
  getServerConfig,
  type ServerConfig,
  type GoogleAccount,
  type ProviderInfo,
  type ServiceInfo,
} from "../api/client.js";
import type { ConnectionItem } from "../components/dialogs/settings/config.js";
import type { Key } from "./useKeypress.js";
import { useProviders } from "./settings/useProviders.js";
import { useServices } from "./settings/useServices.js";
import { useServerConnection } from "./settings/useServerConnection.js";
import { useDirectives } from "./settings/useDirectives.js";
import { useVaultPath } from "./settings/useVaultPath.js";

export interface UseSettingsStateOptions {
  config: Config;
  serverConfig: ServerConfig | null;
  settings: Settings;
  onUpdate: (category: keyof Settings, key: string, value: unknown) => void;
  onServerConfigChange: (config: ServerConfig) => void;
  onServerCredentialsChange: (config: Config) => void;
}

export interface UseSettingsStateResult {
  providers: ProviderInfo[];
  providersIndex: number;
  setProvidersIndex: React.Dispatch<React.SetStateAction<number>>;
  editingProvider: boolean;
  providerKeyValue: string;
  providerKeyCursor: number;
  providerSaving: boolean;
  providerError: string | null;
  providerConfirmDisconnect: boolean;
  setEditingProvider: React.Dispatch<React.SetStateAction<boolean>>;
  setProviderKeyValue: React.Dispatch<React.SetStateAction<string>>;
  setProviderKeyCursor: React.Dispatch<React.SetStateAction<number>>;
  setProviderError: React.Dispatch<React.SetStateAction<string | null>>;
  setProviderConfirmDisconnect: React.Dispatch<React.SetStateAction<boolean>>;
  handleSaveProviderKey: () => Promise<void>;
  handleDisconnectProvider: () => Promise<void>;
  handleProviderKeyInput: (key: Key) => boolean;

  services: ServiceInfo[];
  servicesIndex: number;
  setServicesIndex: React.Dispatch<React.SetStateAction<number>>;
  editingService: boolean;
  serviceKeyValue: string;
  serviceKeyCursor: number;
  serviceSaving: boolean;
  serviceError: string | null;
  serviceConfirmDisconnect: boolean;
  setEditingService: React.Dispatch<React.SetStateAction<boolean>>;
  setServiceKeyValue: React.Dispatch<React.SetStateAction<string>>;
  setServiceKeyCursor: React.Dispatch<React.SetStateAction<number>>;
  setServiceError: React.Dispatch<React.SetStateAction<string | null>>;
  setServiceConfirmDisconnect: React.Dispatch<React.SetStateAction<boolean>>;
  handleSaveServiceKey: () => Promise<void>;
  handleDisconnectService: () => Promise<void>;
  handleServiceKeyInput: (key: Key) => boolean;

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

  directivesContent: string;
  directivesCursorPos: number;
  editingDirectives: boolean;
  savingDirectives: boolean;
  directivesError: string | null;
  handleSaveDirectives: () => Promise<void>;
  handleCancelDirectives: () => void;
  handleStartDirectivesEdit: () => void;
  handleDirectivesKey: (key: Key) => boolean;

  connectionItem: ConnectionItem;
  setConnectionItem: React.Dispatch<React.SetStateAction<ConnectionItem>>;
  googleAccounts: GoogleAccount[];
  selectedGoogleIndex: number;
  setSelectedGoogleIndex: React.Dispatch<React.SetStateAction<number>>;
  actionInProgress: string | null;
  handleAddGoogle: () => Promise<void>;
  handleRemoveGoogle: () => Promise<void>;
  handleToggleSource: (source: string) => Promise<void>;

  editingVault: boolean;
  vaultPath: string;
  vaultCursorPos: number;
  updatingVault: boolean;
  vaultError: string | null;
  handleSaveVault: () => Promise<void>;
  handleCancelVaultEdit: () => void;
  handleStartVaultEdit: () => void;
  handleVaultKey: (key: Key) => boolean;

  showingBrowserDropdown: boolean;
  setShowingBrowserDropdown: React.Dispatch<React.SetStateAction<boolean>>;
  updatingBrowser: boolean;
  browserError: string | null;
  handleSelectBrowser: (browser: string | null) => Promise<void>;

  notifiers: UseNotifiersResult;
  skills: UseSkillsResult;
}

export function useSettingsState({
  config,
  serverConfig,
  settings,
  onUpdate,
  onServerConfigChange,
  onServerCredentialsChange,
}: UseSettingsStateOptions): UseSettingsStateResult {
  const providers = useProviders(config);
  const services = useServices(config);
  const server = useServerConnection(config, onServerCredentialsChange);
  const directives = useDirectives(config);
  const vault = useVaultPath(config, serverConfig, onServerConfigChange);

  // --- Connection state ---
  const [connectionItem, setConnectionItem] = useState<ConnectionItem>("vault");
  const [googleAccounts, setGoogleAccounts] = useState<GoogleAccount[]>([]);
  const [selectedGoogleIndex, setSelectedGoogleIndex] = useState(0);
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);

  // --- Browser state ---
  const [showingBrowserDropdown, setShowingBrowserDropdown] = useState(false);
  const [updatingBrowser, setUpdatingBrowser] = useState(false);
  const [browserError, setBrowserError] = useState<string | null>(null);

  // --- Domain hooks ---
  const notifiers = useNotifiers(config);
  const skills = useSkills(config);

  // --- Initial data loading ---
  useEffect(() => {
    providers.refreshProviders();
    services.refreshServices();
    directives.loadDirectives();
    getGoogleAccounts(config)
      .then((result) => setGoogleAccounts(result.accounts))
      .catch(() => {});
  }, [config]); // eslint-disable-line react-hooks/exhaustive-deps

  // --- Google / connections handlers ---
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

  // --- Browser handler ---
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

  return {
    ...providers,
    ...services,
    ...server,
    ...directives,
    ...vault,

    connectionItem,
    setConnectionItem,
    googleAccounts,
    selectedGoogleIndex,
    setSelectedGoogleIndex,
    actionInProgress,
    handleAddGoogle,
    handleRemoveGoogle,
    handleToggleSource,

    showingBrowserDropdown,
    setShowingBrowserDropdown,
    updatingBrowser,
    browserError,
    handleSelectBrowser,

    notifiers,
    skills,
  };
}
