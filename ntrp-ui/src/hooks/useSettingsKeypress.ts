import { useCallback } from "react";
import { useKeypress, type Key } from "./useKeypress.js";
import type { Settings } from "./useSettings.js";
import type { UseSettingsStateResult } from "./useSettingsState.js";
import type { SectionId } from "../components/dialogs/settings/config.js";
import { SECTION_IDS, LIMIT_ITEMS, CONNECTION_ITEMS, TOGGLEABLE_SOURCES } from "../components/dialogs/settings/config.js";
import type { ServerConfig } from "../api/client.js";

export interface UseSettingsKeypressOptions {
  state: UseSettingsStateResult;
  activeSection: SectionId;
  drilled: boolean;
  setDrilled: React.Dispatch<React.SetStateAction<boolean>>;
  setActiveSection: React.Dispatch<React.SetStateAction<SectionId>>;
  limitsIndex: number;
  setLimitsIndex: React.Dispatch<React.SetStateAction<number>>;
  settings: Settings;
  serverConfig: ServerConfig | null;
  onUpdate: (category: keyof Settings, key: string, value: unknown) => void;
  onClose: () => void;
}

export interface UseSettingsKeypressResult {
  isSectionEditing: () => boolean;
}

export function useSettingsKeypress({
  state,
  activeSection,
  drilled,
  setDrilled,
  setActiveSection,
  limitsIndex,
  setLimitsIndex,
  settings,
  serverConfig,
  onUpdate,
  onClose,
}: UseSettingsKeypressOptions): UseSettingsKeypressResult {
  const {
    providers, providersIndex, setProvidersIndex,
    editingProvider, providerConfirmDisconnect,
    setEditingProvider, setProviderKeyValue, setProviderKeyCursor, setProviderError,
    setProviderConfirmDisconnect,
    handleSaveProviderKey, handleDisconnectProvider, handleProviderKeyInput,

    services, servicesIndex, setServicesIndex,
    editingService, serviceConfirmDisconnect,
    setEditingService, setServiceKeyValue, setServiceKeyCursor, setServiceError,
    setServiceConfirmDisconnect,
    handleSaveServiceKey, handleDisconnectService, handleServiceKeyInput,

    serverIndex, setServerIndex,
    editingServer, serverUrl, serverApiKey,
    setServerUrlCursor, setServerApiKeyCursor, setEditingServer,
    handleSaveServer, handleCancelServerEdit, handleServerUrlKey, handleServerApiKeyKey,

    editingDirectives,
    handleSaveDirectives, handleCancelDirectives, handleStartDirectivesEdit, handleDirectivesKey,

    connectionItem, setConnectionItem,
    googleAccounts, selectedGoogleIndex, setSelectedGoogleIndex,
    actionInProgress,
    handleAddGoogle, handleRemoveGoogle, handleToggleSource,

    editingVault,
    handleCancelVaultEdit, handleStartVaultEdit, handleSaveVault, handleVaultKey,

    showingBrowserDropdown, setShowingBrowserDropdown, updatingVault,

    notifiers, skills,
  } = state;

  const limitsTotalItems = LIMIT_ITEMS.length;

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
    setEditingProvider, setProviderKeyValue, setProviderKeyCursor, setProviderError,
    editingService, serviceConfirmDisconnect,
    setEditingService, setServiceKeyValue, setServiceKeyCursor, setServiceError,
    setProviderConfirmDisconnect, setServiceConfirmDisconnect,
    editingDirectives, handleCancelDirectives,
    editingVault, handleCancelVaultEdit,
    activeSection, notifiers, skills, setDrilled,
  ]);

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
      setProvidersIndex, setProviderKeyValue, setProviderKeyCursor, setProviderError, setEditingProvider, setProviderConfirmDisconnect,
      editingService, serviceConfirmDisconnect, services, servicesIndex, handleServiceKeyInput, handleSaveServiceKey, handleDisconnectService,
      setServicesIndex, setServiceKeyValue, setServiceKeyCursor, setServiceError, setEditingService, setServiceConfirmDisconnect,
      setServerIndex, setServerUrlCursor, setServerApiKeyCursor, setEditingServer,
      setShowingBrowserDropdown, setConnectionItem, setSelectedGoogleIndex,
      setDrilled, setActiveSection, setLimitsIndex,
      undrill, isSectionEditing,
      handleCancelServerEdit, handleCancelDirectives, handleCancelVaultEdit,
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

  return { isSectionEditing };
}
