import { useCallback } from "react";
import type { Config } from "../../types.js";
import type { ProviderInfo } from "../../api/client.js";
import { getProviders, connectProvider, disconnectProvider } from "../../api/client.js";
import { useCredentialSection, type UseCredentialSectionResult } from "./useCredentialSection.js";

export type UseProvidersResult = UseCredentialSectionResult<ProviderInfo>;

export function useProviders(config: Config, onChanged?: () => Promise<void> | void): UseProvidersResult {
  const fetchItems = useCallback(
    () => getProviders(config).then(r => r.providers),
    [config],
  );
  const connectFn = useCallback(
    (id: string, key: string) => connectProvider(config, id, key),
    [config],
  );
  const disconnectFn = useCallback(
    (id: string) => disconnectProvider(config, id),
    [config],
  );

  return useCredentialSection<ProviderInfo>({
    fetchItems,
    connect: connectFn,
    disconnect: disconnectFn,
    canEdit: (p) => p.id !== "custom" && !p.from_env,
    canDisconnect: (p) => p.id !== "custom" && p.connected && !p.from_env,
    onChanged,
  });
}
