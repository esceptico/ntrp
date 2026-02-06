/**
 * Hook for handling slash commands with a registry pattern.
 */
import { useCallback, useRef } from "react";
import type { Config } from "../types.js";
import {
  clearSession,
  purgeMemory,
  compactContext,
  getContextUsage,
  startIndexing,
} from "../api/client.js";

type ViewMode = "chat" | "memory" | "settings" | "schedules";

interface CommandContext {
  config: Config;
  sessionId: string | null;
  messages: { role: string; content: string; id?: string }[];
  // State setters
  setViewMode: (mode: ViewMode) => void;
  updateSessionInfo: (info: { session_id: string; sources: string[] }) => void;
  // Actions
  addMessage: (msg: { role: string; content: string }) => void;
  clearMessages: () => void;
  clearMessageQueue: () => void;
  sendMessage: (msg: string) => void;
  toggleSettings: () => void;
  exit: () => void;
  refreshIndexStatus: () => Promise<void>;
}

type CommandHandler = (ctx: CommandContext) => boolean | Promise<boolean>;

// Command registry - maps command names to handlers
const COMMAND_HANDLERS: Record<string, CommandHandler> = {
  // View commands
  memory: ({ setViewMode }) => {
    setViewMode("memory");
    return true;
  },
  memories: ({ setViewMode }) => {
    setViewMode("memory");
    return true;
  },
  graph: ({ setViewMode }) => {
    setViewMode("memory");
    return true;
  },
  entities: ({ setViewMode }) => {
    setViewMode("memory");
    return true;
  },
  schedules: ({ setViewMode }) => {
    setViewMode("schedules");
    return true;
  },
  schedule: ({ setViewMode }) => {
    setViewMode("schedules");
    return true;
  },
  settings: ({ toggleSettings }) => {
    toggleSettings();
    return true;
  },

  // Actions
  context: async ({ config, addMessage }) => {
    try {
      const ctx = await getContextUsage(config);
      const pct = ((ctx.total / ctx.limit) * 100).toFixed(1);
      const fmt = (n: number) => n.toLocaleString();

      // Build a simple bar visualization
      const barLen = 20;
      const filled = Math.round((ctx.total / ctx.limit) * barLen);
      const bar = "█".repeat(filled) + "░".repeat(barLen - filled);

      const lines = [
        `Context Usage [${bar}] ${pct}%`,
        ``,
        `${ctx.model} · ${fmt(ctx.total)}/${fmt(ctx.limit)} tokens`,
        ``,
        `  System prompt: ${fmt(ctx.system_prompt)} tokens`,
        `  Tool schemas (${ctx.tool_count}): ${fmt(ctx.tools)} tokens`,
        `  Messages (${ctx.message_count}): ${fmt(ctx.messages)} tokens`,
      ];

      addMessage({ role: "assistant", content: lines.join("\n") });
    } catch (error) {
      addMessage({ role: "error", content: `${error}` });
    }
    return true;
  },

  compact: async ({ config, addMessage }) => {
    try {
      addMessage({ role: "status", content: "Compacting context..." });
      const result = await compactContext(config);
      addMessage({ role: "status", content: result.message });
    } catch (error) {
      addMessage({ role: "error", content: `${error}` });
    }
    return true;
  },

  clear: async ({ config, updateSessionInfo, clearMessages, clearMessageQueue, addMessage }) => {
    try {
      const result = await clearSession(config);
      updateSessionInfo({ session_id: result.session_id, sources: [] });
      clearMessageQueue();
      clearMessages();
    } catch (error) {
      addMessage({ role: "error", content: `Failed to clear session: ${error}` });
    }
    return true;
  },

  purge: async ({ config, addMessage }) => {
    try {
      const result = await purgeMemory(config);
      const { facts, links } = result.deleted;
      addMessage({ role: "status", content: `Memory purged: ${facts} facts, ${links} links` });
    } catch (error) {
      addMessage({ role: "error", content: `Failed to purge: ${error}` });
    }
    return true;
  },

  init: ({ addMessage, sendMessage }) => {
    addMessage({ role: "status", content: "Scanning sources and learning about you..." });
    sendMessage("/init");
    return true;
  },

  index: async ({ config, addMessage, refreshIndexStatus }) => {
    try {
      addMessage({ role: "status", content: "Starting indexing..." });
      await startIndexing(config);
      await refreshIndexStatus();
      addMessage({ role: "status", content: "Indexing started. Progress shown in footer." });
    } catch (error) {
      addMessage({ role: "error", content: `Failed to start indexing: ${error}` });
    }
    return true;
  },

  // Model is now in settings
  model: ({ toggleSettings }) => {
    toggleSettings();
    return true;
  },

  // Exit commands
  exit: ({ exit }) => {
    exit();
    return true;
  },
  quit: ({ exit }) => {
    exit();
    return true;
  },
};

export function useCommands(context: CommandContext) {
  const contextRef = useRef(context);
  contextRef.current = context;

  const handleCommand = useCallback(
    async (command: string): Promise<boolean> => {
      const parts = command.toLowerCase().replace("/", "").split(" ");
      const cmd = parts[0];

      const handler = COMMAND_HANDLERS[cmd];
      if (handler) {
        const result = handler(contextRef.current);
        return result instanceof Promise ? await result : result;
      }

      return false;
    },
    []
  );

  return { handleCommand };
}
