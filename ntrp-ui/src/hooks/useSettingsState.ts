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
import { useLimits, type UseLimitsResult } from "./settings/useLimits.js";
import { useSidebarSettings, type UseSidebarSettingsResult } from "./settings/useSidebarSettings.js";

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
  notifiers: UseNotifiersResult;
  skills: UseSkillsResult;
  mcp: UseMCPServersResult;
  limits: UseLimitsResult;
  sidebarSettings: UseSidebarSettingsResult;
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
  const server = useServerConnection(
    config,
    onServerCredentialsChange,
    settings.ui.streaming,
    () => onUpdate("ui", "streaming", !settings.ui.streaming),
  );
  const directives = useDirectives(config);
  const connections = useConnections(config, serverConfig, onServerConfigChange);
  const mcp = useMCPServers(config);
  const limits = useLimits(settings, onUpdate);
  const sidebarSettings = useSidebarSettings(settings, onUpdate);
  const notifiers = useNotifiers(config);
  const skills = useSkills(config);

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
    notifiers,
    skills,
    mcp,
    limits,
    sidebarSettings,
  };
}
