import { useCallback, useRef, useState } from "react";
import type { Config } from "../../types.js";
import type { ProviderInfo } from "../../api/client.js";
import { getProviders, connectProvider, disconnectProvider, connectProviderOAuth } from "../../api/client.js";
import { useCredentialSection, type UseCredentialSectionResult } from "./useCredentialSection.js";

export interface UseProvidersResult extends UseCredentialSectionResult<ProviderInfo> {
  oauthConnecting: boolean;
}

export function useProviders(config: Config): UseProvidersResult {
  const [oauthConnecting, setOauthConnecting] = useState(false);
  const refreshRef = useRef<() => void>(() => {});

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

  const handleOAuthEnter = useCallback((item: ProviderInfo) => {
    if (item.id === "claude_oauth" && !item.connected) {
      setOauthConnecting(true);
      connectProviderOAuth(config, "anthropic")
        .then(() => refreshRef.current())
        .catch(() => {})
        .finally(() => setOauthConnecting(false));
      return true;
    }
    return false;
  }, [config]);

  const section = useCredentialSection<ProviderInfo>({
    fetchItems,
    connect: connectFn,
    disconnect: disconnectFn,
    canEdit: (p) => p.id !== "custom" && p.id !== "claude_oauth" && !p.from_env,
    canDisconnect: (p) => p.id !== "custom" && p.connected && !p.from_env,
    onEnter: handleOAuthEnter,
  });

  refreshRef.current = section.refresh;

  return { ...section, oauthConnecting };
}
