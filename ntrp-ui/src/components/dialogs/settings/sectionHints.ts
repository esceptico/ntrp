import type { SectionId } from "./config.js";
import type { UseSettingsStateResult } from "../../../hooks/useSettingsState.js";
import type { ServerConfig } from "../../../api/client.js";

type HintPair = [string, string];

export function getSectionHints(section: SectionId, state: UseSettingsStateResult, serverConfig: ServerConfig | null): HintPair[] {
  switch (section) {
    case "connection":
      return getConnectionHints(state);
    case "apiKeys":
      return getApiKeysHints(state);
    case "integrations":
      return getIntegrationsHints(state, serverConfig);
    case "instructions":
      return getDirectivesHints(state);
    case "notifications":
      return getNotifiersHints(state);
    case "skills":
      return getSkillsHints(state);
    case "mcp":
      return getMCPHints(state);
    default:
      return [["↑↓", "navigate"], ["enter", "select"], ["←→", "adjust"], ["esc", "back"]];
  }
}

function getConnectionHints(state: UseSettingsStateResult): HintPair[] {
  const s = state.server;
  if (s.editingServer) {
    return [["tab", "switch"], ["^s", "save"], ["esc", "cancel"]];
  }
  if (!s.serverSaving) {
    return [["enter", "edit"], ["esc", "back"]];
  }
  return [["esc", "back"]];
}

function getApiKeysHints(state: UseSettingsStateResult): HintPair[] {
  const { activeList } = state.apiKeys;
  const providers = state.providers;
  const services = state.services;

  if (activeList === "providers") {
    if (providers.editing) {
      return [["enter", "save"], ["esc", "cancel"]];
    }
    const current = providers.items[providers.selectedIndex];
    if (current) {
      if (current.id === "custom") {
        return [["↑↓", "navigate"], ["esc", "back"]];
      }
      const hints: HintPair[] = [["↑↓", "navigate"]];
      if (current.connected && !current.from_env) {
        hints.push(["enter", "edit"], ["d", "disconnect"]);
      } else if (current.from_env) {
        // no action hints - set via env
      } else {
        hints.push(["enter", "add key"]);
      }
      hints.push(["esc", "back"]);
      return hints;
    }
  } else {
    if (services.editing) {
      return [["enter", "save"], ["esc", "cancel"]];
    }
    const current = services.items[services.selectedIndex];
    if (current) {
      const hints: HintPair[] = [["↑↓", "navigate"]];
      if (current.connected && !current.from_env) {
        hints.push(["enter", "edit"], ["d", "disconnect"]);
      } else if (current.from_env) {
        // no action hints
      } else {
        hints.push(["enter", "add key"]);
      }
      hints.push(["esc", "back"]);
      return hints;
    }
  }
  return [["↑↓", "navigate"], ["esc", "back"]];
}

function getIntegrationsHints(state: UseSettingsStateResult, serverConfig: ServerConfig | null): HintPair[] {
  const c = state.connections;
  const item = c.sourceItem;

  if (item === "vault") {
    if (c.vault.editingVault) {
      return [["enter", "save"], ["esc", "cancel"]];
    }
    return [["↑↓", "navigate"], ["enter", "edit path"], ["esc", "back"]];
  }
  if (item === "google") {
    const googleEnabled = serverConfig?.integrations?.google?.enabled;
    if (googleEnabled) {
      return [["↑↓", "navigate"], ["enter", "toggle"], ["a", "add account"], ["d", "remove account"], ["esc", "back"]];
    }
    return [["↑↓", "navigate"], ["enter", "enable"], ["esc", "back"]];
  }
  if (item === "web") {
    return [["↑↓", "navigate"], ["←→", "change mode"], ["esc", "back"]];
  }
  return [["↑↓", "navigate"], ["esc", "back"]];
}

function getDirectivesHints(state: UseSettingsStateResult): HintPair[] {
  const d = state.directives;
  if (d.savingDirectives) {
    return [["esc", "back"]];
  }
  if (d.editingDirectives) {
    return [["^s", "save"], ["esc", "cancel"]];
  }
  return [["enter", "edit"], ["esc", "back"]];
}

function getNotifiersHints(state: UseSettingsStateResult): HintPair[] {
  const n = state.notifiers;
  if (n.loading) return [["esc", "back"]];

  switch (n.mode) {
    case "list":
      if (n.configs.length === 0) {
        return [["a", "add"], ["esc", "back"]];
      }
      return [["↑↓", "navigate"], ["a", "add"], ["e", "edit"], ["t", "test"], ["d", "delete"], ["esc", "back"]];
    case "add-type":
      return [["↑↓", "navigate"], ["enter", "select"], ["esc", "cancel"]];
    case "add-form":
    case "edit-form":
      return [["↑↓", "field"], ["enter", "next/save"], ["^s", "save"], ["esc", "cancel"]];
    case "confirm-delete":
      return [["y", "confirm"], ["n/esc", "cancel"]];
  }
}

function getSkillsHints(state: UseSettingsStateResult): HintPair[] {
  const s = state.skills;
  if (s.loading) return [["esc", "back"]];

  switch (s.mode) {
    case "list":
      if (s.skills.length === 0) {
        return [["a", "install from GitHub"], ["esc", "back"]];
      }
      return [["↑↓", "navigate"], ["a", "install"], ["d", "remove"], ["esc", "back"]];
    case "install":
      return [["enter", "install"], ["esc", "cancel"]];
    case "confirm-delete":
      return [["y", "confirm"], ["n/esc", "cancel"]];
  }
}

function getMCPHints(state: UseSettingsStateResult): HintPair[] {
  const m = state.mcp;

  if (m.mcpMode === "tools") {
    return [["↑↓", "navigate"], ["space", "toggle"], ["a", "all/none"], ["^s", "save"], ["esc", "back"]];
  }

  if (m.mcpMode === "confirm-remove") {
    return [["y", "confirm"], ["n/esc", "cancel"]];
  }

  if (m.mcpMode === "oauth") {
    return [["esc", "back"]];
  }

  if (m.mcpMode === "add") {
    if (!m.mcpSaving) {
      return [["tab", "next"], ["^s", "save"], ["esc", "cancel"]];
    }
    return [["esc", "back"]];
  }

  // list mode
  if (m.mcpSaving) return [["esc", "back"]];

  if (m.mcpServers.length > 0 && m.mcpServers[m.mcpIndex]) {
    const s = m.mcpServers[m.mcpIndex]!;
    const hints: HintPair[] = [["↑↓", "navigate"]];
    if (s.connected) hints.push(["enter", "tools"]);
    hints.push(["a", "add"]);
    hints.push(["e", s.enabled ? "disable" : "enable"]);
    if (s.auth === "oauth" && s.enabled) hints.push(["o", "oauth"]);
    hints.push(["d", "remove"]);
    hints.push(["esc", "back"]);
    return hints;
  }
  return [["a", "add server"], ["esc", "back"]];
}
