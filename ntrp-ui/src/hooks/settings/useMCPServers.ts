import { useCallback, useState } from "react";
import type { Config } from "../../types.js";
import type { MCPServerInfo } from "../../api/client.js";
import { getMCPServers, addMCPServer, removeMCPServer, updateMCPTools, toggleMCPServer, triggerMCPOAuth } from "../../api/client.js";
import { useTextInput } from "../useTextInput.js";
import type { Key } from "../useKeypress.js";
import { handleListNav } from "../keyUtils.js";

export type MCPAddField = "name" | "transport" | "command" | "url" | "auth" | "headers" | "clientId" | "clientSecret";
export type MCPAuth = "none" | "oauth";
export type MCPMode = "list" | "add" | "confirm-remove" | "tools" | "oauth";

export interface UseMCPServersResult {
  mcpServers: MCPServerInfo[];
  mcpIndex: number;
  mcpMode: MCPMode;
  mcpAddField: MCPAddField;
  mcpName: string;
  mcpNameCursor: number;
  mcpTransport: "stdio" | "http";
  mcpAuth: MCPAuth;
  mcpCommand: string;
  mcpCommandCursor: number;
  mcpUrl: string;
  mcpUrlCursor: number;
  mcpHeaders: string;
  mcpHeadersCursor: number;
  mcpClientId: string;
  mcpClientIdCursor: number;
  mcpClientSecret: string;
  mcpClientSecretCursor: number;
  mcpSaving: boolean;
  mcpError: string | null;
  mcpToolIndex: number;
  mcpToolEnabled: boolean[];
  mcpOAuthInProgress: boolean;
  refreshMcpServers: () => void;
  handleKeypress: (key: Key) => void;
  isEditing: boolean;
  cancelEdit: () => void;
}

export function useMCPServers(config: Config): UseMCPServersResult {
  const [mcpServers, setMcpServers] = useState<MCPServerInfo[]>([]);
  const [mcpIndex, setMcpIndex] = useState(0);
  const [mcpMode, setMcpMode] = useState<MCPMode>("list");

  const [mcpAddField, setMcpAddField] = useState<MCPAddField>("name");
  const [mcpName, setMcpName] = useState("");
  const [mcpNameCursor, setMcpNameCursor] = useState(0);
  const [mcpTransport, setMcpTransport] = useState<"stdio" | "http">("stdio");
  const [mcpAuth, setMcpAuth] = useState<MCPAuth>("none");
  const [mcpCommand, setMcpCommand] = useState("");
  const [mcpCommandCursor, setMcpCommandCursor] = useState(0);
  const [mcpUrl, setMcpUrl] = useState("");
  const [mcpUrlCursor, setMcpUrlCursor] = useState(0);
  const [mcpHeaders, setMcpHeaders] = useState("");
  const [mcpHeadersCursor, setMcpHeadersCursor] = useState(0);
  const [mcpClientId, setMcpClientId] = useState("");
  const [mcpClientIdCursor, setMcpClientIdCursor] = useState(0);
  const [mcpClientSecret, setMcpClientSecret] = useState("");
  const [mcpClientSecretCursor, setMcpClientSecretCursor] = useState(0);

  const [mcpSaving, setMcpSaving] = useState(false);
  const [mcpError, setMcpError] = useState<string | null>(null);
  const [mcpOAuthInProgress, setMcpOAuthInProgress] = useState(false);

  // Tool filtering state
  const [mcpToolIndex, setMcpToolIndex] = useState(0);
  const [mcpToolEnabled, setMcpToolEnabled] = useState<boolean[]>([]);

  const { handleKey: handleMcpNameKey } = useTextInput({
    text: mcpName, cursorPos: mcpNameCursor,
    setText: setMcpName, setCursorPos: setMcpNameCursor,
  });
  const { handleKey: handleMcpCommandKey } = useTextInput({
    text: mcpCommand, cursorPos: mcpCommandCursor,
    setText: setMcpCommand, setCursorPos: setMcpCommandCursor,
  });
  const { handleKey: handleMcpUrlKey } = useTextInput({
    text: mcpUrl, cursorPos: mcpUrlCursor,
    setText: setMcpUrl, setCursorPos: setMcpUrlCursor,
  });
  const { handleKey: handleMcpHeadersKey } = useTextInput({
    text: mcpHeaders, cursorPos: mcpHeadersCursor,
    setText: setMcpHeaders, setCursorPos: setMcpHeadersCursor,
  });
  const { handleKey: handleMcpClientIdKey } = useTextInput({
    text: mcpClientId, cursorPos: mcpClientIdCursor,
    setText: setMcpClientId, setCursorPos: setMcpClientIdCursor,
  });
  const { handleKey: handleMcpClientSecretKey } = useTextInput({
    text: mcpClientSecret, cursorPos: mcpClientSecretCursor,
    setText: setMcpClientSecret, setCursorPos: setMcpClientSecretCursor,
  });

  const refreshMcpServers = useCallback(() => {
    getMCPServers(config).then(r => setMcpServers(r.servers)).catch(() => {});
  }, [config]);

  const resetForm = useCallback(() => {
    setMcpName(""); setMcpNameCursor(0);
    setMcpTransport("stdio");
    setMcpAuth("none");
    setMcpCommand(""); setMcpCommandCursor(0);
    setMcpUrl(""); setMcpUrlCursor(0);
    setMcpHeaders(""); setMcpHeadersCursor(0);
    setMcpClientId(""); setMcpClientIdCursor(0);
    setMcpClientSecret(""); setMcpClientSecretCursor(0);
    setMcpError(null);
  }, []);

  const handleMcpAdd = useCallback(async () => {
    if (mcpSaving) return;
    const name = mcpName.trim();
    if (!name) { setMcpError("Name is required"); return; }

    let serverConfig: Record<string, unknown>;
    if (mcpTransport === "stdio") {
      const cmd = mcpCommand.trim();
      if (!cmd) { setMcpError("Command is required"); return; }
      const parts = cmd.split(/\s+/);
      serverConfig = {
        transport: "stdio",
        command: parts[0],
        args: parts.slice(1),
      };
    } else {
      const url = mcpUrl.trim();
      if (!url) { setMcpError("URL is required"); return; }
      serverConfig = { transport: "http", url } as Record<string, unknown>;
      if (mcpAuth === "oauth") {
        serverConfig.auth = "oauth";
        const clientId = mcpClientId.trim();
        const clientSecret = mcpClientSecret.trim();
        if (clientId) serverConfig.client_id = clientId;
        if (clientSecret) serverConfig.client_secret = clientSecret;
      } else {
        const rawHeaders = mcpHeaders.trim();
        if (rawHeaders) {
          const headers: Record<string, string> = {};
          for (const line of rawHeaders.split(",")) {
            const idx = line.indexOf(":");
            if (idx > 0) headers[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
          }
          if (Object.keys(headers).length > 0) serverConfig.headers = headers;
        }
      }
    }

    setMcpSaving(true);
    setMcpError(null);
    try {
      const result = await addMCPServer(config, name, serverConfig);
      if (result.error) {
        setMcpError(result.error);
      }
      refreshMcpServers();
      setMcpMode("list");
    } catch (e) {
      setMcpError(e instanceof Error ? e.message : "Failed to add server");
    } finally {
      setMcpSaving(false);
    }
  }, [mcpSaving, mcpName, mcpTransport, mcpAuth, mcpCommand, mcpUrl, mcpHeaders, mcpClientId, mcpClientSecret, config, refreshMcpServers]);

  const handleMcpRemove = useCallback(async () => {
    if (mcpSaving) return;
    const server = mcpServers[mcpIndex];
    if (!server) return;
    setMcpSaving(true);
    setMcpError(null);
    try {
      await removeMCPServer(config, server.name);
      refreshMcpServers();
      setMcpIndex(i => Math.max(0, i - 1));
    } catch (e) {
      setMcpError(e instanceof Error ? e.message : "Failed to remove");
    } finally {
      setMcpSaving(false);
      setMcpMode("list");
    }
  }, [mcpSaving, mcpServers, mcpIndex, config, refreshMcpServers]);

  const handleSaveTools = useCallback(async () => {
    const server = mcpServers[mcpIndex];
    if (!server || mcpSaving) return;
    const allEnabled = mcpToolEnabled.every(Boolean);
    const serverTools = server.tools ?? [];
    const tools = allEnabled ? null : serverTools
      .filter((_, i) => mcpToolEnabled[i])
      .map(t => t.name);
    setMcpSaving(true);
    setMcpError(null);
    try {
      await updateMCPTools(config, server.name, tools);
      refreshMcpServers();
      setMcpMode("list");
    } catch (e) {
      setMcpError(e instanceof Error ? e.message : "Failed to update tools");
    } finally {
      setMcpSaving(false);
    }
  }, [mcpServers, mcpIndex, mcpToolEnabled, mcpSaving, config, refreshMcpServers]);

  const handleToggleEnabled = useCallback(async () => {
    const server = mcpServers[mcpIndex];
    if (!server || mcpSaving) return;
    setMcpSaving(true);
    setMcpError(null);
    try {
      await toggleMCPServer(config, server.name, !server.enabled);
      refreshMcpServers();
    } catch (e) {
      setMcpError(e instanceof Error ? e.message : "Failed to toggle");
    } finally {
      setMcpSaving(false);
    }
  }, [mcpServers, mcpIndex, mcpSaving, config, refreshMcpServers]);

  const handleOAuth = useCallback(async () => {
    const server = mcpServers[mcpIndex];
    if (!server || mcpOAuthInProgress) return;
    if (server.auth !== "oauth") return;
    setMcpMode("oauth");
    setMcpOAuthInProgress(true);
    setMcpError(null);
    try {
      const result = await triggerMCPOAuth(config, server.name);
      if (result.error) setMcpError(result.error);
      refreshMcpServers();
    } catch (e) {
      setMcpError(e instanceof Error ? e.message : "OAuth failed");
    } finally {
      setMcpOAuthInProgress(false);
      setMcpMode("list");
    }
  }, [mcpServers, mcpIndex, mcpOAuthInProgress, config, refreshMcpServers]);

  const isEditing = mcpMode !== "list";

  const cancelEdit = useCallback(() => {
    setMcpMode("list");
    resetForm();
  }, [resetForm]);

  const handleKeypress = useCallback((key: Key) => {
    if (mcpMode === "confirm-remove") {
      if (key.sequence === "y") handleMcpRemove();
      else setMcpMode("list");
      return;
    }

    if (mcpMode === "tools") {
      const server = mcpServers[mcpIndex];
      if (!server) return;
      const toolCount = (server.tools ?? []).length;
      if (key.name === "s" && key.ctrl) {
        handleSaveTools();
      } else if (key.name === "j" || key.name === "down") {
        setMcpToolIndex(i => Math.min(toolCount - 1, i + 1));
      } else if (key.name === "k" || key.name === "up") {
        setMcpToolIndex(i => Math.max(0, i - 1));
      } else if (key.sequence === " " || key.name === "return") {
        setMcpToolEnabled(prev => {
          const next = [...prev];
          next[mcpToolIndex] = !next[mcpToolIndex];
          return next;
        });
      } else if (key.sequence === "a") {
        setMcpToolEnabled(prev => {
          const allOn = prev.every(Boolean);
          return prev.map(() => !allOn);
        });
      }
      return;
    }

    if (mcpMode === "add") {
      if (key.name === "s" && key.ctrl) {
        handleMcpAdd();
      } else if (key.name === "tab") {
        const fields: MCPAddField[] = mcpTransport === "stdio"
          ? ["name", "transport", "command"]
          : mcpAuth === "oauth"
            ? ["name", "transport", "url", "auth", "clientId", "clientSecret"]
            : ["name", "transport", "url", "auth", "headers"];
        const idx = fields.indexOf(mcpAddField);
        setMcpAddField(fields[(idx + 1) % fields.length]);
      } else if (mcpAddField === "transport") {
        if (key.name === "left" || key.name === "right" || key.name === "h" || key.name === "l") {
          setMcpTransport(t => t === "stdio" ? "http" : "stdio");
        }
      } else if (mcpAddField === "auth") {
        if (key.name === "left" || key.name === "right" || key.name === "h" || key.name === "l") {
          setMcpAuth(a => a === "none" ? "oauth" : "none");
        }
      } else if (mcpAddField === "name") {
        handleMcpNameKey(key);
      } else if (mcpAddField === "command") {
        handleMcpCommandKey(key);
      } else if (mcpAddField === "url") {
        handleMcpUrlKey(key);
      } else if (mcpAddField === "headers") {
        handleMcpHeadersKey(key);
      } else if (mcpAddField === "clientId") {
        handleMcpClientIdKey(key);
      } else if (mcpAddField === "clientSecret") {
        handleMcpClientSecretKey(key);
      }
      return;
    }

    // list mode
    if (handleListNav(key, mcpServers.length, setMcpIndex)) {
      // handled
    } else if (key.sequence === "a") {
      setMcpMode("add");
      setMcpAddField("name");
      resetForm();
    } else if (key.sequence === "e") {
      if (mcpServers.length > 0) handleToggleEnabled();
    } else if (key.sequence === "o") {
      if (mcpServers.length > 0) handleOAuth();
    } else if (key.sequence === "d") {
      if (mcpServers.length > 0) setMcpMode("confirm-remove");
    } else if (key.name === "return" || key.sequence === "t") {
      const server = mcpServers[mcpIndex];
      const tools = server?.tools ?? [];
      if (server?.connected && tools.length > 0) {
        setMcpToolIndex(0);
        setMcpToolEnabled(tools.map(t => t.enabled));
        setMcpError(null);
        setMcpMode("tools");
      }
    }
  }, [
    mcpMode, mcpTransport, mcpAuth, mcpAddField, mcpServers, mcpIndex, mcpToolIndex,
    handleMcpRemove, handleMcpAdd, handleSaveTools, handleToggleEnabled, handleOAuth, resetForm,
    handleMcpNameKey, handleMcpCommandKey, handleMcpUrlKey, handleMcpHeadersKey,
    handleMcpClientIdKey, handleMcpClientSecretKey,
  ]);

  return {
    mcpServers, mcpIndex, mcpMode, mcpAddField,
    mcpName, mcpNameCursor, mcpTransport, mcpAuth,
    mcpCommand, mcpCommandCursor,
    mcpUrl, mcpUrlCursor,
    mcpHeaders, mcpHeadersCursor,
    mcpClientId, mcpClientIdCursor,
    mcpClientSecret, mcpClientSecretCursor,
    mcpSaving, mcpError,
    mcpToolIndex, mcpToolEnabled, mcpOAuthInProgress,
    refreshMcpServers, handleKeypress, isEditing, cancelEdit,
  };
}
