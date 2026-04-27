import { useEffect } from "react";
import type { Config } from "../types.js";
import type { Settings } from "./useSettings.js";
import { useNotifiers, type UseNotifiersResult } from "./useNotifiers.js";
import { useSkills, type UseSkillsResult } from "./useSkills.js";
import type { ServerConfig } from "../api/client.js";
import { useProviders, type UseProvidersResult } from "./settings/useProviders.js";
import { useServices, type UseServicesResult } from "./settings/useServices.js";
import { useServerConnection, type UseServerConnectionResult } from "./settings/useServerConnection.js";
import { useDirectives, type UseDirectivesResult } from "./settings/useDirectives.js";
import { useConnections, type UseConnectionsResult } from "./settings/useConnections.js";
import { useMCPServers, type UseMCPServersResult } from "./settings/useMCPServers.js";
import { useApiKeys, type UseApiKeysResult } from "./settings/useApiKeys.js";
import { useIntegrationsNav, type UseIntegrationsNavResult } from "./settings/useIntegrationsNav.js";
import { useMemorySettings, type UseMemorySettingsResult } from "./settings/useMemorySettings.js";
import { useContextSettings, type UseContextSettingsResult } from "./settings/useContextSettings.js";
import { useAgentSettings, type UseAgentSettingsResult } from "./settings/useAgentSettings.js";
import { useInterfaceSettings, type UseInterfaceSettingsResult } from "./settings/useInterfaceSettings.js";

export interface UseSettingsStateOptions {
  config: Config;
  serverConfig: ServerConfig | null;
  settings: Settings;
  onUpdate: (category: keyof Settings, key: string, value: unknown) => void;
  onServerConfigChange: (config: ServerConfig) => void;
  onServerCredentialsChange: (config: Config) => void;
}

export interface UseSettingsStateResult {
  providers: UseProvidersResult;
  services: UseServicesResult;
  server: UseServerConnectionResult;
  directives: UseDirectivesResult;
  connections: UseConnectionsResult;
  integrationsNav: UseIntegrationsNavResult;
  notifiers: UseNotifiersResult;
  skills: UseSkillsResult;
  mcp: UseMCPServersResult;
  apiKeys: UseApiKeysResult;
  memory: UseMemorySettingsResult;
  context: UseContextSettingsResult;
  agent: UseAgentSettingsResult;
  iface: UseInterfaceSettingsResult;
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
  const connections = useConnections(config, serverConfig, onServerConfigChange);
  const mcp = useMCPServers(config);
  const notifiers = useNotifiers(config);
  const skills = useSkills(config);

  const apiKeys = useApiKeys(providers);
  const integrationsNav = useIntegrationsNav(connections, services);
  const memory = useMemorySettings(config, serverConfig, onServerConfigChange, settings, onUpdate);
  const context = useContextSettings(settings, onUpdate);
  const agent = useAgentSettings(settings, onUpdate);
  const iface = useInterfaceSettings(settings, onUpdate);

  useEffect(() => {
    providers.refresh();
    services.refresh();
    directives.loadDirectives();
    mcp.refreshMcpServers();
  }, [config]); // eslint-disable-line react-hooks/exhaustive-deps

  return {
    providers,
    services,
    server,
    directives,
    connections,
    integrationsNav,
    notifiers,
    skills,
    mcp,
    apiKeys,
    memory,
    context,
    agent,
    iface,
  };
}
