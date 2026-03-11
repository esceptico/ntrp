import { createStore } from "zustand/vanilla";
import type { Message, PendingApproval, TokenUsage } from "../types.js";
import { ZERO_USAGE } from "../types.js";
import type { ToolChainItem } from "../components/toolchain/types.js";
import {
  MAX_MESSAGES,
  MAX_TOOL_MESSAGE_CHARS,
  MAX_ASSISTANT_CHARS,
  Status,
  type Status as StatusType,
} from "../lib/constants.js";
import { truncateText } from "../lib/utils.js";

export type SessionNotification = "streaming" | "done" | "approval" | "error";
export type MessageInput = Omit<Message, "id"> & { id?: string };

export interface ToolTracker {
  descriptions: Map<string, string>;
  startTimes: Map<string, number>;
  sequence: number;
}

export interface SessionStreamState {
  messages: Message[];
  toolChain: ToolChainItem[];
  pendingApproval: PendingApproval | null;
  status: StatusType;
  usage: TokenUsage;
  isStreaming: boolean;
  historyLoaded: boolean;
  runId: string | null;
  pendingText: string;
  currentDepth: number;
  tools: ToolTracker;
  alwaysAllowedTools: Set<string>;
  autoApprovedIds: Set<string>;
  messageIdCounter: number;
  notification: SessionNotification | null;
  backgroundTaskCount: number;
}

function createSessionState(): SessionStreamState {
  return {
    messages: [],
    toolChain: [],
    pendingApproval: null,
    status: Status.IDLE,
    usage: { ...ZERO_USAGE },
    isStreaming: false,
    historyLoaded: false,
    runId: null,
    pendingText: "",
    currentDepth: 0,
    tools: { descriptions: new Map(), startTimes: new Map(), sequence: 0 },
    alwaysAllowedTools: new Set(),
    autoApprovedIds: new Set(),
    messageIdCounter: 0,
    notification: null,
    backgroundTaskCount: 0,
  };
}

export interface StreamingStore {
  sessions: Map<string, SessionStreamState>;
  viewedId: string | null;

  getSession: (id: string) => SessionStreamState;
  mutateSession: (id: string, fn: (s: SessionStreamState) => void) => void;
  addMessageToSession: (s: SessionStreamState, msg: MessageInput) => void;
  finalizeText: (s: SessionStreamState) => void;
  setViewedId: (id: string) => void;
  deleteSession: (id: string) => void;

}

export function createStreamingStore() {
  return createStore<StreamingStore>((set, get) => {
    function generateId(s: SessionStreamState): string {
      return `m-${Date.now()}-${s.messageIdCounter++}`;
    }

    function addMessageToSession(s: SessionStreamState, msg: MessageInput) {
      const content = msg.role === "tool"
        ? truncateText(msg.content, MAX_TOOL_MESSAGE_CHARS, 'end')
        : msg.content;
      const withId: Message = { ...msg, content, id: msg.id ?? generateId(s) } as Message;
      const updated = [...s.messages, withId];
      s.messages = updated.length > MAX_MESSAGES ? updated.slice(-MAX_MESSAGES) : updated;
    }

    function finalizeText(s: SessionStreamState) {
      s.currentDepth = 0;
      const finalContent = truncateText(s.pendingText, MAX_ASSISTANT_CHARS, 'end');
      s.pendingText = "";
      if (finalContent) addMessageToSession(s, { role: "assistant", content: finalContent });
    }

    function replaceSession(id: string, s: SessionStreamState) {
      const sessions = new Map(get().sessions);
      sessions.set(id, {
        ...s,
        tools: { ...s.tools, descriptions: new Map(s.tools.descriptions), startTimes: new Map(s.tools.startTimes) },
        alwaysAllowedTools: new Set(s.alwaysAllowedTools),
        autoApprovedIds: new Set(s.autoApprovedIds),
      });
      set({ sessions });
    }

    return {
      sessions: new Map(),
      viewedId: null,

      getSession(id: string): SessionStreamState {
        const { sessions } = get();
        let s = sessions.get(id);
        if (!s) {
          s = createSessionState();
          replaceSession(id, s);
        }
        return s;
      },

      mutateSession(id: string, fn: (s: SessionStreamState) => void) {
        const s = get().getSession(id);
        fn(s);
        replaceSession(id, s);
      },

      addMessageToSession,
      finalizeText,

      setViewedId(id: string) {
        set({ viewedId: id });
      },

      deleteSession(id: string) {
        const sessions = new Map(get().sessions);
        sessions.delete(id);
        set({ sessions });
      },
    };
  });
}
