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
import { deleteCredentials } from "../lib/secrets.js";

type ViewMode = "chat" | "memory" | "automations";

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
  openDialog: (id: string) => void;
  exit: () => void;
  refreshIndexStatus: () => Promise<void>;
  createNewSession: (name?: string) => Promise<string | null>;
  switchSession: (sessionId: string) => Promise<{ history: HistoryMessage[] } | null>;
  switchToSession: (sessionId: string, history?: Message[]) => void;
  deleteSessionState: (sessionId: string) => void;
  revert: () => Promise<string | null>;
  refreshSidebar: () => void;
  logout: () => void;
}

type CommandHandler = (ctx: CommandContext, args: string[]) => boolean | Promise<boolean>;

const COMMAND_HANDLERS: Record<string, CommandHandler> = {
  connect: ({ openDialog }) => { openDialog("providers"); return true; },
  memory: ({ setViewMode }) => { setViewMode("memory"); return true; },
  automations: ({ setViewMode }) => { setViewMode("automations"); return true; },
  theme: ({ openDialog }) => { openDialog("theme"); return true; },
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

  purge: async ({ config, addMessage }, args) => {
    if (args[0] !== "confirm") {
      addMessage({ role: "status", content: "This will delete all memory facts and links. Type /purge confirm to proceed." });
      return true;
    }
    try {
      const result = await purgeMemory(config);
      const { facts, links } = result.deleted;
      addMessage({ role: "status", content: `Memory purged: ${facts} facts, ${links} links` });
    } catch (error) {
      addMessage({ role: "error", content: `Failed to purge: ${error}` });
    }
    return true;
  },

  retry: async ({ addMessage, sendMessage, revert }) => {
    const userMessage = await revert();
    if (!userMessage) {
      addMessage({ role: "error", content: "Nothing to retry" });
      return true;
    }
    sendMessage(userMessage);
    return true;
  },

  undo: async ({ addMessage, revert }) => {
    const userMessage = await revert();
    if (!userMessage) {
      addMessage({ role: "error", content: "Nothing to undo" });
      return true;
    }
    addMessage({ role: "status", content: `Reverted: ${userMessage.length > 100 ? userMessage.slice(0, 100) + "…" : userMessage}` });
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

  new: async ({ addMessage, createNewSession, switchToSession, refreshSidebar }, args) => {
    const name = args.join(" ").trim() || undefined;
    const newId = await createNewSession(name);
    if (newId) {
      switchToSession(newId, []);
      refreshSidebar();
    } else {
      addMessage({ role: "error", content: "Failed to create session" });
    }
    return true;
  },

  sessions: ({ openDialog }) => { openDialog("sessions"); return true; },

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

  delete: async ({ config, sessionId, addMessage, createNewSession, switchToSession, deleteSessionState, switchSession, refreshSidebar }, args) => {
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

      deleteSessionState(targetId);
      await deleteSession(config, targetId);

      if (targetId === sessionId) {
        const next = sessions.find(s => s.session_id !== targetId);
        if (next) {
          const result = await switchSession(next.session_id);
          if (result) {
            switchToSession(next.session_id, result.history.map((msg, i) => ({
              id: `h-${i}`, role: msg.role, content: msg.content,
            })));
          } else {
            const newId = await createNewSession();
            if (newId) switchToSession(newId, []);
          }
        } else {
          const newId = await createNewSession();
          if (newId) switchToSession(newId, []);
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

  logout: async ({ logout }) => {
    await deleteCredentials();
    logout();
    return true;
  },

  models: ({ openDialog }) => { openDialog("models"); return true; },
  model: ({ openDialog }) => { openDialog("models"); return true; },
  exit: ({ exit }) => { exit(); return true; },
  quit: ({ exit }) => { exit(); return true; },
};

export function useCommands(context: CommandContext) {
  const contextRef = useRef(context);
  contextRef.current = context;

  const handleCommand = useCallback(
    async (command: string): Promise<boolean> => {
      const parts = command.slice(1).split(" ");
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
