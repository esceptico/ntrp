import { useCallback, useRef } from "react";
import type { Config } from "../types.js";
import type { HistoryMessage } from "../api/client.js";
import type { Message } from "../types.js";
import { Status, type Status as StatusType } from "../lib/constants.js";
import {
  clearSession,
  purgeMemory,
  compactContext,
  startIndexing,
  listSessions,
  listArchivedSessions,
  renameSession,
  deleteSession,
  restoreSession,
  type SessionListItem,
} from "../api/client.js";

type ViewMode = "chat" | "memory" | "settings" | "schedules" | "dashboard" | "sessions";

function findSession(sessions: SessionListItem[], query: string): SessionListItem | undefined {
  const q = query.toLowerCase();
  return (
    sessions.find(s => s.session_id === query || s.name?.toLowerCase() === q) ||
    sessions.find(s => s.session_id.includes(query) || s.name?.toLowerCase().includes(q))
  );
}

interface CommandContext {
  config: Config;
  sessionId: string | null;
  messages: { role: string; content: string; id?: string }[];
  setViewMode: (mode: ViewMode) => void;
  updateSessionInfo: (info: { session_id: string; sources?: string[]; session_name?: string }) => void;
  addMessage: (msg: { role: string; content: string }) => void;
  clearMessages: () => void;
  sendMessage: (msg: string) => void;
  setStatus: (status: StatusType) => void;
  toggleSettings: () => void;
  openThemePicker: () => void;
  exit: () => void;
  refreshIndexStatus: () => Promise<void>;
  createNewSession: (name?: string) => Promise<string | null>;
  switchSession: (sessionId: string) => Promise<{ history: HistoryMessage[] } | null>;
  resetForSessionSwitch: (newHistory?: Message[]) => void;
  refreshSidebar: () => void;
}

type CommandHandler = (ctx: CommandContext, args: string[]) => boolean | Promise<boolean>;

const COMMAND_HANDLERS: Record<string, CommandHandler> = {
  memory: ({ setViewMode }) => { setViewMode("memory"); return true; },
  schedules: ({ setViewMode }) => { setViewMode("schedules"); return true; },
  dashboard: ({ setViewMode }) => { setViewMode("dashboard"); return true; },
  theme: ({ openThemePicker }) => { openThemePicker(); return true; },
  settings: ({ toggleSettings }) => { toggleSettings(); return true; },

  compact: async ({ config, sessionId, addMessage, setStatus }) => {
    try {
      setStatus(Status.COMPRESSING);
      const result = await compactContext(config, sessionId ?? undefined);
      addMessage({ role: "status", content: result.message });
    } catch (error) {
      addMessage({ role: "error", content: `${error}` });
    } finally {
      setStatus(Status.IDLE);
    }
    return true;
  },

  clear: async ({ config, sessionId, clearMessages, addMessage }) => {
    try {
      await clearSession(config, sessionId ?? undefined);
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

  new: async ({ addMessage, createNewSession, resetForSessionSwitch, refreshSidebar }, args) => {
    const name = args.join(" ").trim() || undefined;
    const newId = await createNewSession(name);
    if (newId) {
      resetForSessionSwitch([]);
      refreshSidebar();
    } else {
      addMessage({ role: "error", content: "Failed to create session" });
    }
    return true;
  },

  sessions: ({ setViewMode }) => { setViewMode("sessions"); return true; },

  name: async ({ config, sessionId, addMessage, updateSessionInfo, refreshSidebar }, args) => {
    const name = args.join(" ").trim();
    if (!name) {
      addMessage({ role: "error", content: "Usage: /name <session name>" });
      return true;
    }
    if (!sessionId) {
      addMessage({ role: "error", content: "No active session" });
      return true;
    }
    try {
      await renameSession(config, sessionId, name);
      updateSessionInfo({ session_id: sessionId, session_name: name });
      refreshSidebar();
    } catch (error) {
      addMessage({ role: "error", content: `${error}` });
    }
    return true;
  },

  delete: async ({ config, sessionId, addMessage, createNewSession, resetForSessionSwitch, switchSession, refreshSidebar }, args) => {
    const query = args.join(" ").trim();
    try {
      const { sessions } = await listSessions(config);

      let targetId: string;
      if (query) {
        const match = findSession(sessions, query);
        if (!match) {
          addMessage({ role: "error", content: `No session matching "${query}"` });
          return true;
        }
        targetId = match.session_id;
      } else if (sessionId) {
        targetId = sessionId;
      } else {
        addMessage({ role: "error", content: "No active session" });
        return true;
      }

      await deleteSession(config, targetId);

      if (targetId === sessionId) {
        const next = sessions.find(s => s.session_id !== targetId);
        if (next) {
          const result = await switchSession(next.session_id);
          if (result) {
            resetForSessionSwitch(result.history.map((msg, i) => ({
              id: `h-${i}`, role: msg.role, content: msg.content,
            })));
          } else {
            await createNewSession();
            resetForSessionSwitch([]);
          }
        } else {
          await createNewSession();
          resetForSessionSwitch([]);
        }
      }

      refreshSidebar();
    } catch (error) {
      addMessage({ role: "error", content: `${error}` });
    }
    return true;
  },

  restore: async ({ config, addMessage, refreshSidebar }, args) => {
    const query = args.join(" ").trim();
    if (!query) {
      addMessage({ role: "error", content: "Usage: /restore <session name or id>" });
      return true;
    }
    try {
      const { sessions } = await listArchivedSessions(config);
      const match = findSession(sessions, query);
      if (!match) {
        addMessage({ role: "error", content: `No archived session matching "${query}"` });
        return true;
      }
      await restoreSession(config, match.session_id);
      addMessage({ role: "status", content: `Restored session "${match.name || match.session_id}"` });
      refreshSidebar();
    } catch (error) {
      addMessage({ role: "error", content: `${error}` });
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
      const parts = command.replace("/", "").split(" ");
      const cmd = parts[0].toLowerCase();

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
