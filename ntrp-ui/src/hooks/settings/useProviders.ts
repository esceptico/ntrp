import { useCallback, useState } from "react";
import type { Config } from "../../types.js";
import type { ProviderInfo } from "../../api/client.js";
import { getProviders, connectProvider, disconnectProvider } from "../../api/client.js";
import { useTextInput } from "../useTextInput.js";
import type { Key } from "../useKeypress.js";

export interface UseProvidersResult {
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
  refreshProviders: () => void;
}

export function useProviders(config: Config): UseProvidersResult {
  const [providersIndex, setProvidersIndex] = useState(0);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [editingProvider, setEditingProvider] = useState(false);
  const [providerKeyValue, setProviderKeyValue] = useState("");
  const [providerKeyCursor, setProviderKeyCursor] = useState(0);
  const [providerSaving, setProviderSaving] = useState(false);
  const [providerError, setProviderError] = useState<string | null>(null);
  const [providerConfirmDisconnect, setProviderConfirmDisconnect] = useState(false);

  const { handleKey: handleProviderKeyInput } = useTextInput({
    text: providerKeyValue,
    cursorPos: providerKeyCursor,
    setText: setProviderKeyValue,
    setCursorPos: setProviderKeyCursor,
  });

  const refreshProviders = useCallback(() => {
    getProviders(config).then(r => setProviders(r.providers)).catch(() => {});
  }, [config]);

  const handleSaveProviderKey = useCallback(async () => {
    if (providerSaving) return;
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
  }, [providerSaving, providerKeyValue, providers, providersIndex, config, refreshProviders]);

  const handleDisconnectProvider = useCallback(async () => {
    if (providerSaving) return;
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
  }, [providerSaving, providers, providersIndex, config, refreshProviders]);

  return {
    providers,
    providersIndex,
    setProvidersIndex,
    editingProvider,
    providerKeyValue,
    providerKeyCursor,
    providerSaving,
    providerError,
    providerConfirmDisconnect,
    setEditingProvider,
    setProviderKeyValue,
    setProviderKeyCursor,
    setProviderError,
    setProviderConfirmDisconnect,
    handleSaveProviderKey,
    handleDisconnectProvider,
    handleProviderKeyInput,
    refreshProviders,
  };
}
