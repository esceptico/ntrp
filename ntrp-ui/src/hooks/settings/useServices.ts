import { useCallback } from "react";
import type { Config } from "../../types.js";
import type { ServiceInfo } from "../../api/client.js";
import { getServices, connectService, disconnectService } from "../../api/client.js";
import { useCredentialSection, type UseCredentialSectionResult } from "./useCredentialSection.js";

export type UseServicesResult = UseCredentialSectionResult<ServiceInfo>;

export function useServices(config: Config): UseServicesResult {
  const fetchItems = useCallback(
    () => getServices(config).then(r => r.services),
    [config],
  );
  const connectFn = useCallback(
    (id: string, key: string) => connectService(config, id, key),
    [config],
  );
  const disconnectFn = useCallback(
    (id: string) => disconnectService(config, id),
    [config],
  );

  return useCredentialSection<ServiceInfo>({
    fetchItems,
    connect: connectFn,
    disconnect: disconnectFn,
  });
}
