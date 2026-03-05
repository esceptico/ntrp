import { useCallback, useState } from "react";
import type { Config } from "../../types.js";
import type { MCPServerInfo } from "../../api/client.js";
import { getMCPServers, addMCPServer, removeMCPServer } from "../../api/client.js";
import { useTextInput } from "../useTextInput.js";
import type { Key } from "../useKeypress.js";
import { handleListNav } from "../keyUtils.js";

export interface UseMCPServersResult {
  mcpServers: MCPServerInfo[];
  mcpIndex: number;
  mcpAdding: boolean;
  mcpAddField: "name" | "transport" | "command" | "url";
  mcpName: string;
  mcpNameCursor: number;
  mcpTransport: "stdio" | "http";
  mcpCommand: string;
  mcpCommandCursor: number;
  mcpUrl: string;
  mcpUrlCursor: number;
  mcpSaving: boolean;
  mcpError: string | null;
  mcpConfirmRemove: boolean;
  refreshMcpServers: () => void;
  handleKeypress: (key: Key) => void;
  isEditing: boolean;
  cancelEdit: () => void;
}

export function useMCPServers(config: Config): UseMCPServersResult {
  const [mcpServers, setMcpServers] = useState<MCPServerInfo[]>([]);
  const [mcpIndex, setMcpIndex] = useState(0);

  const [mcpAdding, setMcpAdding] = useState(false);
  const [mcpAddField, setMcpAddField] = useState<"name" | "transport" | "command" | "url">("name");

  const [mcpName, setMcpName] = useState("");
  const [mcpNameCursor, setMcpNameCursor] = useState(0);
  const [mcpTransport, setMcpTransport] = useState<"stdio" | "http">("stdio");
  const [mcpCommand, setMcpCommand] = useState("");
  const [mcpCommandCursor, setMcpCommandCursor] = useState(0);
  const [mcpUrl, setMcpUrl] = useState("");
  const [mcpUrlCursor, setMcpUrlCursor] = useState(0);

  const [mcpSaving, setMcpSaving] = useState(false);
  const [mcpError, setMcpError] = useState<string | null>(null);
  const [mcpConfirmRemove, setMcpConfirmRemove] = useState(false);

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

  const refreshMcpServers = useCallback(() => {
    getMCPServers(config).then(r => setMcpServers(r.servers)).catch(() => {});
  }, [config]);

  const handleMcpStartAdd = useCallback(() => {
    setMcpAdding(true);
    setMcpAddField("name");
    setMcpName("");
    setMcpNameCursor(0);
    setMcpTransport("stdio");
    setMcpCommand("");
    setMcpCommandCursor(0);
    setMcpUrl("");
    setMcpUrlCursor(0);
    setMcpError(null);
  }, []);

  const handleMcpCancelAdd = useCallback(() => {
    setMcpAdding(false);
    setMcpName("");
    setMcpNameCursor(0);
    setMcpTransport("stdio");
    setMcpCommand("");
    setMcpCommandCursor(0);
    setMcpUrl("");
    setMcpUrlCursor(0);
    setMcpError(null);
  }, []);

  const handleMcpToggleTransport = useCallback(() => {
    setMcpTransport(t => t === "stdio" ? "http" : "stdio");
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
      serverConfig = { transport: "http", url };
    }

    setMcpSaving(true);
    setMcpError(null);
    try {
      const result = await addMCPServer(config, name, serverConfig);
      if (result.error) {
        setMcpError(result.error);
      }
      refreshMcpServers();
      setMcpAdding(false);
    } catch (e) {
      setMcpError(e instanceof Error ? e.message : "Failed to add server");
    } finally {
      setMcpSaving(false);
    }
  }, [mcpSaving, mcpName, mcpTransport, mcpCommand, mcpUrl, config, refreshMcpServers]);

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
      setMcpConfirmRemove(false);
    }
  }, [mcpSaving, mcpServers, mcpIndex, config, refreshMcpServers]);

  const isEditing = mcpAdding || mcpConfirmRemove;

  const cancelEdit = useCallback(() => {
    if (mcpAdding) handleMcpCancelAdd();
    else if (mcpConfirmRemove) setMcpConfirmRemove(false);
  }, [mcpAdding, mcpConfirmRemove, handleMcpCancelAdd]);

  const handleKeypress = useCallback((key: Key) => {
    if (mcpConfirmRemove) {
      if (key.sequence === "y") handleMcpRemove();
      else setMcpConfirmRemove(false);
      return;
    }
    if (mcpAdding) {
      if (key.name === "s" && key.ctrl) {
        handleMcpAdd();
      } else if (key.name === "tab") {
        const fields = mcpTransport === "stdio"
          ? ["name", "transport", "command"] as const
          : ["name", "transport", "url"] as const;
        const idx = (fields as readonly string[]).indexOf(mcpAddField);
        setMcpAddField(fields[(idx + 1) % fields.length]);
      } else if (mcpAddField === "transport") {
        if (key.name === "left" || key.name === "right" || key.name === "h" || key.name === "l") {
          handleMcpToggleTransport();
        }
      } else if (mcpAddField === "name") {
        handleMcpNameKey(key);
      } else if (mcpAddField === "command") {
        handleMcpCommandKey(key);
      } else if (mcpAddField === "url") {
        handleMcpUrlKey(key);
      }
      return;
    }
    if (handleListNav(key, mcpServers.length, setMcpIndex)) {
      // handled
    } else if (key.sequence === "a") {
      handleMcpStartAdd();
    } else if (key.sequence === "d") {
      if (mcpServers.length > 0) setMcpConfirmRemove(true);
    }
  }, [
    mcpConfirmRemove, mcpAdding, mcpTransport, mcpAddField, mcpServers.length,
    handleMcpRemove, handleMcpAdd, handleMcpToggleTransport,
    handleMcpNameKey, handleMcpCommandKey, handleMcpUrlKey, handleMcpStartAdd,
  ]);

  return {
    mcpServers,
    mcpIndex,
    mcpAdding,
    mcpAddField,
    mcpName,
    mcpNameCursor,
    mcpTransport,
    mcpCommand,
    mcpCommandCursor,
    mcpUrl,
    mcpUrlCursor,
    mcpSaving,
    mcpError,
    mcpConfirmRemove,
    refreshMcpServers,
    handleKeypress,
    isEditing,
    cancelEdit,
  };
}
