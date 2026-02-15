import { useCallback, useRef } from "react";
import type { Config } from "../types.js";
import { Status, type Status as StatusType } from "../lib/constants.js";
import {
  clearSession,
  purgeMemory,
  compactContext,
  startIndexing,
} from "../api/client.js";

type ViewMode = "chat" | "memory" | "settings" | "schedules" | "dashboard";

interface CommandContext {
  config: Config;
  sessionId: string | null;
  messages: { role: string; content: string; id?: string }[];
  setViewMode: (mode: ViewMode) => void;
  updateSessionInfo: (info: { session_id: string; sources: string[] }) => void;
  addMessage: (msg: { role: string; content: string }) => void;
  clearMessages: () => void;
  sendMessage: (msg: string) => void;
  setStatus: (status: StatusType) => void;
  toggleSettings: () => void;
  openThemePicker: () => void;
  exit: () => void;
  refreshIndexStatus: () => Promise<void>;
}

type CommandHandler = (ctx: CommandContext, args: string[]) => boolean | Promise<boolean>;

const COMMAND_HANDLERS: Record<string, CommandHandler> = {
  memory: ({ setViewMode }) => { setViewMode("memory"); return true; },
  memories: ({ setViewMode }) => { setViewMode("memory"); return true; },
  graph: ({ setViewMode }) => { setViewMode("memory"); return true; },
  entities: ({ setViewMode }) => { setViewMode("memory"); return true; },
  schedules: ({ setViewMode }) => { setViewMode("schedules"); return true; },
  schedule: ({ setViewMode }) => { setViewMode("schedules"); return true; },
  dashboard: ({ setViewMode }) => { setViewMode("dashboard"); return true; },
  theme: ({ openThemePicker }) => { openThemePicker(); return true; },
  settings: ({ toggleSettings }) => { toggleSettings(); return true; },

  compact: async ({ config, addMessage, setStatus }) => {
    try {
      setStatus(Status.COMPRESSING);
      const result = await compactContext(config);
      addMessage({ role: "status", content: result.message });
    } catch (error) {
      addMessage({ role: "error", content: `${error}` });
    } finally {
      setStatus(Status.IDLE);
    }
    return true;
  },

  clear: async ({ config, updateSessionInfo, clearMessages, addMessage }) => {
    try {
      const result = await clearSession(config);
      updateSessionInfo({ session_id: result.session_id, sources: [] });
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
      await startIndexing(config);
      await refreshIndexStatus();
    } catch (error) {
      addMessage({ role: "error", content: `Failed to start indexing: ${error}` });
    }
    return true;
  },

  model: ({ toggleSettings }) => { toggleSettings(); return true; },
  exit: ({ exit }) => { exit(); return true; },
  quit: ({ exit }) => { exit(); return true; },
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
        const result = handler(contextRef.current, parts.slice(1));
        return result instanceof Promise ? await result : result;
      }

      return false;
    },
    []
  );

  return { handleCommand };
}
