import { useCallback, useEffect, useState } from "react";
import type { Config } from "../../../types.js";
import type { Settings } from "../../../hooks/useSettings.js";
import { useKeypress, type Key } from "../../../hooks/useKeypress.js";
import { Dialog, colors, Hints } from "../../ui/index.js";
import { useAccentColor } from "../../../hooks/index.js";
import {
  getGoogleAccounts,
  addGoogleAccount,
  removeGoogleAccount,
  updateConfig,
  updateVaultPath,
  updateBrowser,
  getServerConfig,
  getDirectives,
  updateDirectives,
  getProviders,
  connectProvider,
  disconnectProvider,
  getServices,
  connectService,
  disconnectService,
  type ServerConfig,
  type GoogleAccount,
  type ProviderInfo,
  type ServiceInfo,
} from "../../../api/client.js";
import { SectionId, SECTION_IDS, SECTION_LABELS, LIMIT_ITEMS, CONNECTION_ITEMS, TOGGLEABLE_SOURCES, type ConnectionItem } from "./config.js";
import { DialogSelect, type SelectOption } from "../../ui/index.js";
import { ConnectionsSection } from "./ConnectionsSection.js";
import { DirectivesSection, LimitsSection, NotifiersSection, ProvidersSection, ServerSection, ServicesSection, SkillsSection } from "./sections/index.js";
import { setCredentials } from "../../../lib/secrets.js";
import { checkHealth } from "../../../api/client.js";
import { setApiKey as setFetchApiKey } from "../../../api/fetch.js";
import { useTextInput } from "../../../hooks/useTextInput.js";
import { useNotifiers } from "../../../hooks/useNotifiers.js";
import { useSkills } from "../../../hooks/useSkills.js";

interface SettingsDialogProps {
  config: Config;
  serverConfig: ServerConfig | null;
  settings: Settings;
  onUpdate: (category: keyof Settings, key: string, value: unknown) => void;
  onServerConfigChange: (config: ServerConfig) => void;
  onRefreshIndexStatus: () => Promise<void>;
  onClose: () => void;
  onServerCredentialsChange: (config: Config) => void;
}

export function SettingsDialog({
  config,
  serverConfig,
  settings,
  onUpdate,
  onServerConfigChange,
  onRefreshIndexStatus,
  onClose,
  onServerCredentialsChange,
}: SettingsDialogProps) {
  const { accentValue: accent } = useAccentColor();

  const [activeSection, setActiveSection] = useState<SectionId>("server");
  const [drilled, setDrilled] = useState(false);
  const [limitsIndex, setLimitsIndex] = useState(0);

  const [providersIndex, setProvidersIndex] = useState(0);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [editingProvider, setEditingProvider] = useState(false);
  const [providerKeyValue, setProviderKeyValue] = useState("");
  const [providerKeyCursor, setProviderKeyCursor] = useState(0);
  const [providerSaving, setProviderSaving] = useState(false);
  const [providerError, setProviderError] = useState<string | null>(null);
  const [providerConfirmDisconnect, setProviderConfirmDisconnect] = useState(false);

  const [servicesIndex, setServicesIndex] = useState(0);
  const [services, setServices] = useState<ServiceInfo[]>([]);
  const [editingService, setEditingService] = useState(false);
  const [serviceKeyValue, setServiceKeyValue] = useState("");
  const [serviceKeyCursor, setServiceKeyCursor] = useState(0);
  const [serviceSaving, setServiceSaving] = useState(false);
  const [serviceError, setServiceError] = useState<string | null>(null);
  const [serviceConfirmDisconnect, setServiceConfirmDisconnect] = useState(false);

  const [serverIndex, setServerIndex] = useState(0);
  const [editingServer, setEditingServer] = useState(false);
  const [serverUrl, setServerUrl] = useState(config.serverUrl);
  const [serverUrlCursor, setServerUrlCursor] = useState(0);
  const [serverApiKey, setServerApiKey] = useState(config.apiKey);
  const [serverApiKeyCursor, setServerApiKeyCursor] = useState(0);
  const [serverSaving, setServerSaving] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const [connectionItem, setConnectionItem] = useState<ConnectionItem>("vault");
  const [googleAccounts, setGoogleAccounts] = useState<GoogleAccount[]>([]);
  const [selectedGoogleIndex, setSelectedGoogleIndex] = useState(0);
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);

  const [editingVault, setEditingVault] = useState(false);
  const [vaultPath, setVaultPath] = useState(serverConfig?.vault_path || "");
  const [vaultCursorPos, setVaultCursorPos] = useState(0);
  const [updatingVault, setUpdatingVault] = useState(false);
  const [vaultError, setVaultError] = useState<string | null>(null);

  const [showingBrowserDropdown, setShowingBrowserDropdown] = useState(false);
  const [updatingBrowser, setUpdatingBrowser] = useState(false);
  const [browserError, setBrowserError] = useState<string | null>(null);

  const [directivesContent, setDirectivesContent] = useState("");
  const [directivesSaved, setDirectivesSaved] = useState("");
  const [directivesCursorPos, setDirectivesCursorPos] = useState(0);
  const [editingDirectives, setEditingDirectives] = useState(false);
  const [savingDirectives, setSavingDirectives] = useState(false);

  const notifiers = useNotifiers(config);
  const skills = useSkills(config);

  const { handleKey: handleProviderKeyInput } = useTextInput({
    text: providerKeyValue,
    cursorPos: providerKeyCursor,
    setText: setProviderKeyValue,
    setCursorPos: setProviderKeyCursor,
  });

  const { handleKey: handleServiceKeyInput } = useTextInput({
    text: serviceKeyValue,
    cursorPos: serviceKeyCursor,
    setText: setServiceKeyValue,
    setCursorPos: setServiceKeyCursor,
  });

  const refreshProviders = useCallback(() => {
    getProviders(config).then(r => setProviders(r.providers)).catch(() => {});
  }, [config]);

  const refreshServices = useCallback(() => {
    getServices(config).then(r => setServices(r.services)).catch(() => {});
  }, [config]);

  useEffect(() => {
    refreshProviders();
    refreshServices();
    getGoogleAccounts(config)
      .then((result) => setGoogleAccounts(result.accounts))
      .catch(() => {});
    getDirectives(config)
      .then((result) => {
        setDirectivesContent(result.content);
        setDirectivesSaved(result.content);
      })
      .catch(() => {});
  }, [config]); // eslint-disable-line react-hooks/exhaustive-deps

  const limitsTotalItems = LIMIT_ITEMS.length;

  // --- Provider key editing ---

  const handleSaveProviderKey = useCallback(async () => {
    const key = providerKeyValue.trim();
    const provider = providers[providersIndex];
    if (!key || !provider || provider.id === "custom") return;

    setProviderSaving(true);
    setProviderError(null);
    try {
      await connectProvider(config, provider.id, key);
      refreshProviders();
      setEditingProvider(false);
      setProviderKeyValue("");
      setProviderKeyCursor(0);
    } catch (e) {
      setProviderError(e instanceof Error ? e.message : "Failed to connect");
    } finally {
      setProviderSaving(false);
    }
  }, [providerKeyValue, providers, providersIndex, config, refreshProviders]);

  const handleDisconnectProvider = useCallback(async () => {
    const provider = providers[providersIndex];
    if (!provider) return;
    setProviderSaving(true);
    setProviderError(null);
    try {
      await disconnectProvider(config, provider.id);
      refreshProviders();
    } catch (e) {
      setProviderError(e instanceof Error ? e.message : "Failed to disconnect");
    } finally {
      setProviderSaving(false);
      setProviderConfirmDisconnect(false);
    }
  }, [providers, providersIndex, config, refreshProviders]);

  // --- Service key editing ---

  const handleSaveServiceKey = useCallback(async () => {
    const key = serviceKeyValue.trim();
    const service = services[servicesIndex];
    if (!key || !service) return;

    setServiceSaving(true);
    setServiceError(null);
    try {
      await connectService(config, service.id, key);
      refreshServices();
      setEditingService(false);
      setServiceKeyValue("");
      setServiceKeyCursor(0);
    } catch (e) {
      setServiceError(e instanceof Error ? e.message : "Failed to connect");
    } finally {
      setServiceSaving(false);
    }
  }, [serviceKeyValue, services, servicesIndex, config, refreshServices]);

  const handleDisconnectService = useCallback(async () => {
    const service = services[servicesIndex];
    if (!service) return;
    setServiceSaving(true);
    setServiceError(null);
    try {
      await disconnectService(config, service.id);
      refreshServices();
    } catch (e) {
      setServiceError(e instanceof Error ? e.message : "Failed to disconnect");
    } finally {
      setServiceSaving(false);
      setServiceConfirmDisconnect(false);
    }
  }, [services, servicesIndex, config, refreshServices]);

  // --- Google / connections ---

  const handleAddGoogle = useCallback(async () => {
    if (actionInProgress) return;
    setActionInProgress("Adding account...");
    try {
      await addGoogleAccount(config);
      const accounts = await getGoogleAccounts(config);
      setGoogleAccounts(accounts.accounts);
    } catch {
    } finally {
      setActionInProgress(null);
    }
  }, [config, actionInProgress]);

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
    } catch {
    } finally {
      setActionInProgress(null);
    }
  }, [config, googleAccounts, selectedGoogleIndex, actionInProgress]);

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

  const { handleKey: handleDirectivesKey } = useTextInput({
    text: directivesContent,
    cursorPos: directivesCursorPos,
    setText: setDirectivesContent,
    setCursorPos: setDirectivesCursorPos,
  });

  const handleSaveDirectives = useCallback(async () => {
    if (savingDirectives) return;
    setSavingDirectives(true);
    try {
      const result = await updateDirectives(config, directivesContent);
      setDirectivesSaved(result.content);
      setDirectivesContent(result.content);
      setEditingDirectives(false);
    } catch {
    } finally {
      setSavingDirectives(false);
    }
  }, [config, directivesContent, savingDirectives]);

  const handleCancelDirectives = useCallback(() => {
    setDirectivesContent(directivesSaved);
    setDirectivesCursorPos(0);
    setEditingDirectives(false);
  }, [directivesSaved]);

  const handleStartDirectivesEdit = useCallback(() => {
    setDirectivesCursorPos(directivesContent.length);
    setEditingDirectives(true);
  }, [directivesContent]);

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

  // --- Undrill helper: reset section-specific editing state ---
  const undrill = useCallback(() => {
    if (editingServer) { handleCancelServerEdit(); return; }
    if (editingProvider) { setEditingProvider(false); setProviderKeyValue(""); setProviderKeyCursor(0); setProviderError(null); return; }
    if (providerConfirmDisconnect) { setProviderConfirmDisconnect(false); return; }
    if (editingService) { setEditingService(false); setServiceKeyValue(""); setServiceKeyCursor(0); setServiceError(null); return; }
    if (serviceConfirmDisconnect) { setServiceConfirmDisconnect(false); return; }
    if (editingDirectives) { handleCancelDirectives(); return; }
    if (editingVault) { handleCancelVaultEdit(); return; }
    if (activeSection === "notifiers" && notifiers.mode !== "list") { notifiers.handleKeypress({ name: "escape" } as Key); return; }
    if (activeSection === "skills" && skills.mode !== "list") { skills.handleKeypress({ name: "escape" } as Key); return; }
    setDrilled(false);
  }, [
    editingServer, handleCancelServerEdit,
    editingProvider, providerConfirmDisconnect,
    editingService, serviceConfirmDisconnect,
    editingDirectives, handleCancelDirectives,
    editingVault, handleCancelVaultEdit,
    activeSection, notifiers, skills,
  ]);

  // Check if section has active inline editing
  const isSectionEditing = useCallback(() => {
    if (activeSection === "server" && editingServer) return true;
    if (activeSection === "providers" && (editingProvider || providerConfirmDisconnect)) return true;
    if (activeSection === "services" && (editingService || serviceConfirmDisconnect)) return true;
    if (activeSection === "directives" && editingDirectives) return true;
    if (activeSection === "connections" && editingVault) return true;
    if (activeSection === "notifiers" && notifiers.mode !== "list") return true;
    if (activeSection === "skills" && skills.mode !== "list") return true;
    return false;
  }, [activeSection, editingServer, editingProvider, providerConfirmDisconnect, editingService, serviceConfirmDisconnect, editingDirectives, editingVault, notifiers.mode, skills.mode]);

  const handleKeypress = useCallback(
    (key: Key) => {
      if (actionInProgress) return;

      // --- Escape ---
      if (key.name === "escape" || key.name === "q") {
        if (drilled) {
          if (isSectionEditing()) {
            undrill();
          } else {
            setDrilled(false);
          }
          return;
        }
        onClose();
        return;
      }

      // --- Section-level navigation (not drilled) ---
      if (!drilled) {
        const idx = SECTION_IDS.indexOf(activeSection);
        if (key.name === "up" || key.name === "k") {
          if (idx > 0) setActiveSection(SECTION_IDS[idx - 1]);
          return;
        }
        if (key.name === "down" || key.name === "j") {
          if (idx < SECTION_IDS.length - 1) setActiveSection(SECTION_IDS[idx + 1]);
          return;
        }
        if (key.name === "return" || key.name === "space") {
          setDrilled(true);
          return;
        }
        return;
      }

      // --- Drilled into section ---

      if (activeSection === "providers") {
        if (providerConfirmDisconnect) {
          if (key.sequence === "y") handleDisconnectProvider();
          else setProviderConfirmDisconnect(false);
          return;
        }
        if (editingProvider) {
          if (key.name === "return") {
            handleSaveProviderKey();
          } else {
            handleProviderKeyInput(key);
          }
          return;
        }
        if (key.name === "up" || key.name === "k") {
          setProvidersIndex(i => Math.max(0, i - 1));
        } else if (key.name === "down" || key.name === "j") {
          setProvidersIndex(i => Math.min(providers.length - 1, i + 1));
        } else if (key.name === "return" || key.name === "space") {
          const p = providers[providersIndex];
          if (p && p.id !== "custom" && !p.from_env) {
            setProviderKeyValue("");
            setProviderKeyCursor(0);
            setProviderError(null);
            setEditingProvider(true);
          }
        } else if (key.sequence === "d") {
          const p = providers[providersIndex];
          if (p && p.id !== "custom" && p.connected && !p.from_env) {
            setProviderConfirmDisconnect(true);
          }
        }
      } else if (activeSection === "services") {
        if (serviceConfirmDisconnect) {
          if (key.sequence === "y") handleDisconnectService();
          else setServiceConfirmDisconnect(false);
          return;
        }
        if (editingService) {
          if (key.name === "return") {
            handleSaveServiceKey();
          } else {
            handleServiceKeyInput(key);
          }
          return;
        }
        if (key.name === "up" || key.name === "k") {
          setServicesIndex(i => Math.max(0, i - 1));
        } else if (key.name === "down" || key.name === "j") {
          setServicesIndex(i => Math.min(services.length - 1, i + 1));
        } else if (key.name === "return" || key.name === "space") {
          const s = services[servicesIndex];
          if (s && !s.from_env) {
            setServiceKeyValue("");
            setServiceKeyCursor(0);
            setServiceError(null);
            setEditingService(true);
          }
        } else if (key.sequence === "d") {
          const s = services[servicesIndex];
          if (s && s.connected && !s.from_env) {
            setServiceConfirmDisconnect(true);
          }
        }
      } else if (activeSection === "server") {
        if (editingServer) {
          if (key.name === "s" && key.ctrl) {
            handleSaveServer();
          } else if (key.name === "tab") {
            setServerIndex((i) => (i === 0 ? 1 : 0));
          } else if (serverIndex === 0) {
            handleServerUrlKey(key);
          } else {
            handleServerApiKeyKey(key);
          }
        } else {
          if (key.name === "up" || key.name === "k") {
            setServerIndex((i) => Math.max(0, i - 1));
          } else if (key.name === "down" || key.name === "j") {
            setServerIndex((i) => Math.min(1, i + 1));
          } else if (key.name === "return" || key.name === "space") {
            setServerUrlCursor(serverUrl.length);
            setServerApiKeyCursor(serverApiKey.length);
            setEditingServer(true);
          }
        }
      } else if (activeSection === "directives") {
        if (editingDirectives) {
          if (key.name === "s" && key.ctrl) {
            handleSaveDirectives();
          } else {
            handleDirectivesKey(key);
          }
        } else if (key.name === "return" || key.name === "space") {
          handleStartDirectivesEdit();
        }
      } else if (activeSection === "connections") {
        const connIdx = CONNECTION_ITEMS.indexOf(connectionItem);
        const isGoogleSource = connectionItem === "gmail" || connectionItem === "calendar";
        const sourceEnabled = isGoogleSource && serverConfig?.sources?.[connectionItem]?.enabled;
        const hasAccountList = sourceEnabled && googleAccounts.length > 0;

        if (key.name === "up" || key.name === "k") {
          if (hasAccountList && selectedGoogleIndex > 0) {
            setSelectedGoogleIndex((i) => i - 1);
          } else if (connIdx > 0) {
            setConnectionItem(CONNECTION_ITEMS[connIdx - 1]);
            setSelectedGoogleIndex(0);
          }
        } else if (key.name === "down" || key.name === "j") {
          if (hasAccountList && selectedGoogleIndex < googleAccounts.length - 1) {
            setSelectedGoogleIndex((i) => i + 1);
          } else if (connIdx < CONNECTION_ITEMS.length - 1) {
            setConnectionItem(CONNECTION_ITEMS[connIdx + 1]);
            setSelectedGoogleIndex(0);
          }
        } else if (key.name === "return" || key.name === "space") {
          if (connectionItem === "vault") {
            handleStartVaultEdit();
          } else if (connectionItem === "browser") {
            setShowingBrowserDropdown(true);
          } else if (TOGGLEABLE_SOURCES.includes(connectionItem)) {
            handleToggleSource(connectionItem);
          }
        } else if (key.sequence === "a" && isGoogleSource && sourceEnabled) {
          handleAddGoogle();
        } else if ((key.sequence === "d" || key.name === "delete") && isGoogleSource && sourceEnabled) {
          handleRemoveGoogle();
        }
      } else if (activeSection === "skills") {
        skills.handleKeypress(key);
      } else if (activeSection === "notifiers") {
        notifiers.handleKeypress(key);
      } else if (activeSection === "limits") {
        if (key.name === "up" || key.name === "k") {
          setLimitsIndex((i) => Math.max(0, i - 1));
        } else if (key.name === "down" || key.name === "j") {
          setLimitsIndex((i) => Math.min(limitsTotalItems - 1, i + 1));
        } else if (key.name === "left" || key.name === "h") {
          const item = LIMIT_ITEMS[limitsIndex];
          const val = settings.agent[item.key as keyof typeof settings.agent] as number;
          if (val > item.min) onUpdate("agent", item.key, val - 1);
        } else if (key.name === "right" || key.name === "l") {
          const item = LIMIT_ITEMS[limitsIndex];
          const val = settings.agent[item.key as keyof typeof settings.agent] as number;
          if (val < item.max) onUpdate("agent", item.key, val + 1);
        }
      }
    },
    [
      activeSection, limitsIndex, drilled,
      limitsTotalItems,
      settings, onUpdate, onClose, actionInProgress,
      connectionItem, googleAccounts, selectedGoogleIndex, serverConfig,
      handleAddGoogle, handleRemoveGoogle, handleStartVaultEdit, handleToggleSource,
      notifiers, skills,
      editingServer, serverIndex, serverUrl, serverApiKey, handleServerUrlKey, handleServerApiKeyKey, handleSaveServer,
      editingDirectives, handleDirectivesKey, handleSaveDirectives, handleStartDirectivesEdit,
      editingProvider, providerConfirmDisconnect, providers, providersIndex, handleProviderKeyInput, handleSaveProviderKey, handleDisconnectProvider,
      editingService, serviceConfirmDisconnect, services, servicesIndex, handleServiceKeyInput, handleSaveServiceKey, handleDisconnectService,
      undrill, isSectionEditing,
    ]
  );

  const handleVaultEditKeypress = useCallback(
    (key: Key) => {
      if (key.name === "escape") {
        handleCancelVaultEdit();
        return;
      }
      if (key.name === "return") {
        handleSaveVault();
        return;
      }
      handleVaultKey(key);
    },
    [handleVaultKey, handleSaveVault, handleCancelVaultEdit]
  );

  useKeypress(handleKeypress, { isActive: !editingVault && !showingBrowserDropdown });
  useKeypress(handleVaultEditKeypress, { isActive: editingVault && !updatingVault });

  const browserOptions: SelectOption<string | null>[] = [
    { value: "chrome", title: "Chrome", indicator: serverConfig?.browser === "chrome" ? "●" : undefined },
    { value: "safari", title: "Safari", indicator: serverConfig?.browser === "safari" ? "●" : undefined },
    { value: "arc", title: "Arc", indicator: serverConfig?.browser === "arc" ? "●" : undefined },
    { value: null, title: "None (disable)", indicator: serverConfig?.browser == null ? "●" : undefined },
  ];

  if (showingBrowserDropdown) {
    return (
      <DialogSelect<string | null>
        title="Browser"
        options={browserOptions}
        initialIndex={Math.max(0, browserOptions.findIndex(o => o.value === (serverConfig?.browser || null)))}
        onSelect={(opt) => handleSelectBrowser(opt.value)}
        onClose={() => setShowingBrowserDropdown(false)}
      />
    );
  }

  const footerHints = drilled
    ? [["↑↓", "navigate"], ["enter", "select"], ["←→", "adjust"], ["esc", "back"]] as [string, string][]
    : [["↑↓", "section"], ["enter", "open"], ["esc", "close"]] as [string, string][];

  return (
    <Dialog
      title="PREFERENCES"
      size="large"
      onClose={onClose}
      footer={<Hints items={footerHints} />}
    >
      {({ width, height }) => {
        const sidebarWidth = 16;
        const detailWidth = Math.max(0, width - sidebarWidth - 3);
        const contentHeight = Math.max(1, height - 1);

        return (
          <>
            <box flexDirection="row">
              {/* Sidebar */}
              <box flexDirection="column" width={sidebarWidth}>
                {SECTION_IDS.map((section) => {
                  const isActive = section === activeSection;
                  return (
                    <text key={section}>
                      <span fg={isActive ? accent : colors.text.disabled}>{isActive ? "▸ " : "  "}</span>
                      {isActive ? (
                        <span fg={accent}><strong>{SECTION_LABELS[section]}</strong></span>
                      ) : (
                        <span fg={colors.text.secondary}>{SECTION_LABELS[section]}</span>
                      )}
                    </text>
                  );
                })}
              </box>

              {/* Divider */}
              <box flexDirection="column" width={1} marginX={1}>
                {Array.from({ length: contentHeight }).map((_, i) => (
                  <text key={i}><span fg={colors.divider}>│</span></text>
                ))}
              </box>

              {/* Detail pane */}
              <box flexDirection="column" width={detailWidth} height={contentHeight} overflow="hidden">
                {activeSection === "providers" && (
                  <ProvidersSection
                    providers={providers}
                    selectedIndex={providersIndex}
                    accent={accent}
                    editing={editingProvider}
                    keyValue={providerKeyValue}
                    keyCursor={providerKeyCursor}
                    saving={providerSaving}
                    error={providerError}
                    confirmingDisconnect={providerConfirmDisconnect}
                  />
                )}

                {activeSection === "services" && (
                  <ServicesSection
                    services={services}
                    selectedIndex={servicesIndex}
                    accent={accent}
                    editing={editingService}
                    keyValue={serviceKeyValue}
                    keyCursor={serviceKeyCursor}
                    saving={serviceSaving}
                    error={serviceError}
                    confirmingDisconnect={serviceConfirmDisconnect}
                  />
                )}

                {activeSection === "server" && (
                  <ServerSection
                    serverUrl={serverUrl}
                    serverUrlCursor={serverUrlCursor}
                    apiKey={serverApiKey}
                    apiKeyCursor={serverApiKeyCursor}
                    selectedIndex={serverIndex}
                    editing={editingServer}
                    accent={accent}
                    saving={serverSaving}
                    error={serverError}
                  />
                )}

                {activeSection === "directives" && (
                  <DirectivesSection
                    content={directivesContent}
                    cursorPos={directivesCursorPos}
                    editing={editingDirectives}
                    saving={savingDirectives}
                    accent={accent}
                    height={contentHeight}
                  />
                )}

                {activeSection === "skills" && (
                  <SkillsSection skills={skills} accent={accent} width={detailWidth} />
                )}

                {activeSection === "connections" && (
                  <ConnectionsSection
                    serverConfig={serverConfig}
                    googleAccounts={googleAccounts}
                    selectedItem={connectionItem}
                    selectedGoogleIndex={selectedGoogleIndex}
                    accent={accent}
                    width={detailWidth}
                    editingVault={editingVault}
                    vaultPath={vaultPath}
                    vaultCursorPos={vaultCursorPos}
                    updatingVault={updatingVault}
                    vaultError={vaultError}
                    updatingBrowser={updatingBrowser}
                    browserError={browserError}
                  />
                )}

                {activeSection === "notifiers" && (
                  <NotifiersSection notifiers={notifiers} accent={accent} />
                )}

                {activeSection === "limits" && (
                  <LimitsSection
                    settings={settings.agent}
                    selectedIndex={limitsIndex}
                    accent={accent}
                  />
                )}
              </box>
            </box>

            {actionInProgress && (
              <box marginTop={1}>
                <text><span fg={colors.status.warning}>{actionInProgress}</span></text>
              </box>
            )}
          </>
        );
      }}
    </Dialog>
  );
}
