import { create } from "zustand";
import {
  type AppConfig,
  type ArchivedSession,
  type Automation,
  type HistoryPage,
  type ModelsResponse,
  type ServerConfig,
  type SessionListItem,
  type SkillDescriptor,
  DEFAULT_CONFIG,
} from "./api";
import type { MessageSourceFocus } from "./lib/messageSourceFocus";

export type Role = "user" | "assistant" | "reasoning" | "tool" | "status" | "error" | "activity" | "approval";

export type ThinkingAnimation =
  | "comet"
  | "breath"
  | "hue-cycle"
  | "send-orbit";

export type ThinkingIntensity = "subtle" | "normal" | "strong";

export type ThemeChoice = "light" | "dark" | "system";

export type PaletteId =
  | "warm"
  | "graphite"
  | "vercel"
  | "raycast"
  | "github"
  | "linear"
  | "notion"
  | "catppuccin";

export interface Prefs {
  thinkingAnimation: ThinkingAnimation;
  thinkingIntensity: ThinkingIntensity;
  theme: ThemeChoice;
  palette: PaletteId;
  sidebarHidden: boolean;
  /** Sidebar width in pixels. User-resizable via the right-edge drag
   *  handle. Clamped to [SIDEBAR_MIN_WIDTH, SIDEBAR_MAX_WIDTH] in the
   *  resize handler. Default matches the historic fixed width. */
  sidebarWidth: number;
  showReasoningInChat: boolean;
}

export const SIDEBAR_MIN_WIDTH = 200;
export const SIDEBAR_MAX_WIDTH = 380;
export const SIDEBAR_SNAP_POINTS = [220, 244, 280, 320] as const;
export const SIDEBAR_SNAP_THRESHOLD_PX = 12;

const PREFS_KEY = "ntrp.desktop.prefs";
const PREFS_VERSION = 2;
const DEFAULT_PREFS: Prefs = {
  thinkingAnimation: "comet",
  thinkingIntensity: "normal",
  theme: "system",
  palette: "graphite",
  sidebarHidden: false,
  sidebarWidth: 244,
  showReasoningInChat: true,
};

function loadPrefs(): Prefs {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    if (!raw) return DEFAULT_PREFS;
    const parsed = JSON.parse(raw) as Partial<Prefs> & { prefsVersion?: number };
    // One-time migration: bump anyone still on the legacy "warm" default
    // to graphite when introducing the new default. Users who explicitly
    // want warm can flip back from Settings → Appearance.
    if ((parsed.prefsVersion ?? 1) < PREFS_VERSION && parsed.palette === "warm") {
      parsed.palette = "graphite";
    }
    return { ...DEFAULT_PREFS, ...parsed };
  } catch {
    return DEFAULT_PREFS;
  }
}

function persistPrefs(prefs: Prefs): void {
  try {
    localStorage.setItem(
      PREFS_KEY,
      JSON.stringify({ ...prefs, prefsVersion: PREFS_VERSION }),
    );
  } catch {
    /* localStorage unavailable — non-fatal */
  }
}

export interface ActivityItem {
  id: string;
  /** Tool name (used for display + inspector lookup). Despite the name this
   *  is the tool's identifier — see `semanticKind` for "tool vs agent". */
  kind: string;
  /** Semantic kind from the server: "tool" (default) or "agent" for tools
   *  that internally spawn a sub-agent. The renderer picks a different row
   *  surface for agents. */
  semanticKind?: string;
  target: string;
  args?: string;
  result?: string;
  /** Nesting depth: 0 = top-level (called by the user-facing agent),
   *  1 = inside a sub-agent (research → research, etc.). Used purely for
   *  visualization (indent + chip). */
  depth?: number;
  /** Tool-call id of the parent tool whose run produced this call.
   *  Available for nested calls; lets the inspector group children. */
  parentToolId?: string;
  /** Server-reported error flag (set on TOOL_CALL_RESULT). Lets the
   *  trace render error rows distinctly without parsing the result text. */
  error?: boolean;
  /** Wall-clock duration of the tool call in milliseconds. Set on
   *  TOOL_CALL_RESULT — undefined while running. */
  durationMs?: number;
}

export interface ActivityState {
  items: ActivityItem[];
  label: string;
  done: boolean;
}

export type ApprovalStatus = "pending" | "approved" | "rejected";

export interface ApprovalState {
  toolId: string;
  toolName: string;
  path?: string;
  diff?: string;
  preview?: string;
  status: ApprovalStatus;
}

export interface TurnMeta {
  startedAt: number;
  endedAt: number | null;
  durationMs: number | null;
}

export interface ImageBlock {
  /** IANA media type, e.g. "image/png". */
  media_type: string;
  /** Base64-encoded image bytes (no data: URL prefix). */
  data: string;
}

export interface UiMessage {
  id: string;
  role: Role;
  sourceIndex?: number;
  sourceMessageId?: string;
  title?: string;
  subtitle?: string;
  content: string;
  activity?: ActivityState;
  approval?: ApprovalState;
  turn?: TurnMeta;
  images?: ImageBlock[];
}

export interface SessionUsage {
  lastPrompt: number;
  totalTokens: number;
  totalCost: number;
}

interface State {
  config: AppConfig;
  sessions: SessionListItem[];
  currentSessionId: string | null;
  messages: Map<string, UiMessage>;
  order: string[];
  /** Set to the session id whose saved history is now loaded into
   *  `messages`/`order`. We delay opening the SSE stream until this
   *  matches `currentSessionId` — otherwise `setHistory()` racing the
   *  first live deltas would wipe them. */
  historyLoadedFor: string | null;
  historyHasMoreBefore: boolean;
  historyHasMoreAfter: boolean;
  historyLoadingBefore: boolean;
  historyLoadingAfter: boolean;
  /** Session ids with an active run on the server. Refreshed by a
   *  poller hook so the sidebar can render a streaming indicator on
   *  sessions that are still working — including the ones the user
   *  isn't currently viewing. */
  activeRunSessionIds: Set<string>;
  /** Sessions whose runs finished while the user wasn't looking at
   *  them. Cleared when the user opens the session. Renders as an
   *  "unread" dot in the sidebar. */
  unreadDoneSessionIds: Set<string>;
  connected: boolean;
  running: boolean;
  error: string | null;
  draft: string;
  settingsOpen: boolean;
  connectionDraft: AppConfig;
  connectionError: string | null;
  connectionSaving: boolean;
  usage: SessionUsage;
  editingId: string | null;
  activeActivityId: string | null;
  currentRunId: string | null;
  skipApprovals: boolean;
  skills: SkillDescriptor[];
  commandPickerOpen: boolean;
  commandPickerIndex: number;
  selectedSkill: SkillDescriptor | null;
  viewingMarkdown: MarkdownViewState | null;
  viewingTool: ActivityItem | null;
  pendingImages: ImageBlock[];
  serverConfig: ServerConfig | null;
  serverModels: ModelsResponse | null;
  automations: Automation[] | null;
  automationsOpen: boolean;
  archiveOpen: boolean;
  archivedSessions: ArchivedSession[] | null;
  compacting: boolean;
  lastCompaction: { before: number; after: number; at: number } | null;
  memoryOpen: boolean;
  sourceFocus: MessageSourceFocus | null;
  paletteOpen: boolean;
  prefs: Prefs;
}

export interface MarkdownViewState {
  title: string;
  subtitle?: string;
  content: string;
  /** Optional filesystem path — surfaces an "open in OS" affordance. */
  sourcePath?: string;
}

interface Actions {
  setConfig: (config: AppConfig) => void;
  setSessions: (sessions: SessionListItem[]) => void;
  prependSession: (session: SessionListItem) => void;
  setActiveRunSessions: (ids: string[]) => void;
  setCurrentSession: (sessionId: string | null) => void;
  setHistory: (messages: UiMessage[], page?: HistoryPage) => void;
  prependHistory: (messages: UiMessage[], page?: HistoryPage) => void;
  appendHistoryPage: (messages: UiMessage[], page?: HistoryPage) => void;
  setHistoryLoading: (direction: "before" | "after", loading: boolean) => void;
  appendMessage: (message: UiMessage) => void;
  insertMessageBefore: (message: UiMessage, beforeId: string | null) => void;
  mutateMessage: (id: string, patch: Partial<UiMessage>) => void;
  truncateFrom: (id: string) => void;
  setConnected: (connected: boolean) => void;
  setRunning: (running: boolean) => void;
  setError: (error: string | null) => void;
  setDraft: (draft: string) => void;
  setEditingId: (id: string | null) => void;
  resetUsage: () => void;
  accumulateUsage: (usage: { prompt: number; completion: number; cost: number }) => void;
  openSettings: () => void;
  closeSettings: () => void;
  setConnectionDraft: (patch: Partial<AppConfig>) => void;
  setConnectionError: (error: string | null) => void;
  setConnectionSaving: (saving: boolean) => void;
  setActiveActivityId: (id: string | null) => void;
  appendActivityItem: (activityId: string, item: ActivityItem) => void;
  mergeActivityItem: (itemId: string, patch: Partial<ActivityItem>) => void;
  finalizeActivity: (activityId: string, label?: string) => void;
  setCurrentRunId: (runId: string | null) => void;
  setSkipApprovals: (skip: boolean) => void;
  setApprovalStatus: (id: string, status: ApprovalStatus) => void;
  setSkills: (skills: SkillDescriptor[]) => void;
  setCommandPickerOpen: (open: boolean) => void;
  setCommandPickerIndex: (index: number) => void;
  setSelectedSkill: (skill: SkillDescriptor | null) => void;
  setViewingMarkdown: (view: MarkdownViewState | null) => void;
  setViewingTool: (item: ActivityItem | null) => void;
  addPendingImages: (images: ImageBlock[]) => void;
  removePendingImage: (index: number) => void;
  clearPendingImages: () => void;
  setServerConfig: (cfg: ServerConfig | null) => void;
  setServerModels: (models: ModelsResponse | null) => void;
  setAutomations: (automations: Automation[] | null) => void;
  openAutomations: () => void;
  closeAutomations: () => void;
  setArchivedSessions: (sessions: ArchivedSession[] | null) => void;
  openArchive: () => void;
  closeArchive: () => void;
  setCompacting: (compacting: boolean) => void;
  setLastCompaction: (info: State["lastCompaction"]) => void;
  openMemory: () => void;
  closeMemory: () => void;
  setSourceFocus: (focus: MessageSourceFocus | null) => void;
  openPalette: () => void;
  closePalette: () => void;
  togglePalette: () => void;
  setPref: <K extends keyof Prefs>(key: K, value: Prefs[K]) => void;
  toggleSidebar: () => void;
}

const initialUsage: SessionUsage = { lastPrompt: 0, totalTokens: 0, totalCost: 0 };

export const useStore = create<State & Actions>((set) => ({
  config: { ...DEFAULT_CONFIG },
  sessions: [],
  currentSessionId: null,
  messages: new Map(),
  order: [],
  historyLoadedFor: null,
  historyHasMoreBefore: false,
  historyHasMoreAfter: false,
  historyLoadingBefore: false,
  historyLoadingAfter: false,
  activeRunSessionIds: new Set(),
  unreadDoneSessionIds: new Set(),
  connected: false,
  running: false,
  error: null,
  draft: "",
  settingsOpen: false,
  connectionDraft: { ...DEFAULT_CONFIG },
  connectionError: null,
  connectionSaving: false,
  usage: initialUsage,
  editingId: null,
  activeActivityId: null,
  currentRunId: null,
  skipApprovals: false,
  skills: [],
  commandPickerOpen: false,
  commandPickerIndex: 0,
  selectedSkill: null,
  viewingMarkdown: null,
  viewingTool: null,
  pendingImages: [],
  serverConfig: null,
  serverModels: null,
  automations: null,
  automationsOpen: false,
  archiveOpen: false,
  archivedSessions: null,
  compacting: false,
  lastCompaction: null,
  memoryOpen: false,
  sourceFocus: null,
  paletteOpen: false,
  prefs: loadPrefs(),

  setConfig: (config) => set({ config, connectionDraft: { ...config } }),
  setSessions: (sessions) => set({ sessions }),
  prependSession: (session) => set((s) => ({ sessions: [session, ...s.sessions] })),
  setActiveRunSessions: (ids) =>
    set((s) => {
      const next = new Set(ids);
      // Sessions that just transitioned active → idle are "unread done"
      // unless the user is currently viewing them.
      const newlyDone: string[] = [];
      for (const prev of s.activeRunSessionIds) {
        if (!next.has(prev) && prev !== s.currentSessionId) {
          newlyDone.push(prev);
        }
      }

      let unread = s.unreadDoneSessionIds;
      if (newlyDone.length > 0) {
        unread = new Set(unread);
        for (const id of newlyDone) unread.add(id);
      }

      // Skip the activeRunSessionIds update if nothing changed by membership.
      let activeChanged = next.size !== s.activeRunSessionIds.size || newlyDone.length > 0;
      if (!activeChanged) {
        for (const id of next) {
          if (!s.activeRunSessionIds.has(id)) {
            activeChanged = true;
            break;
          }
        }
      }

      if (!activeChanged && unread === s.unreadDoneSessionIds) return {};
      return {
        ...(activeChanged ? { activeRunSessionIds: next } : {}),
        ...(unread !== s.unreadDoneSessionIds ? { unreadDoneSessionIds: unread } : {}),
      };
    }),
  setCurrentSession: (currentSessionId) =>
    set((s) => {
      let unread = s.unreadDoneSessionIds;
      if (currentSessionId && unread.has(currentSessionId)) {
        unread = new Set(unread);
        unread.delete(currentSessionId);
      }
      return {
        currentSessionId,
        messages: new Map(),
        order: [],
        usage: initialUsage,
        editingId: null,
        activeActivityId: null,
        currentRunId: null,
        // The previous session's RUN_FINISHED arrives on a bus we no
        // longer subscribe to — reset here so we don't carry a stale
        // "thinking" indicator into the new session. loadHistory turns
        // it back on if the destination session is itself in-flight.
        running: false,
        compacting: false,
        lastCompaction: null,
        sourceFocus: null,
        historyLoadedFor: null,
        historyHasMoreBefore: false,
        historyHasMoreAfter: false,
        historyLoadingBefore: false,
        historyLoadingAfter: false,
        ...(unread !== s.unreadDoneSessionIds ? { unreadDoneSessionIds: unread } : {}),
      };
    }),

  setHistory: (messages, page) =>
    set((s) => {
      const map = new Map<string, UiMessage>();
      const order: string[] = [];
      for (const m of messages) {
        map.set(m.id, m);
        order.push(m.id);
      }
      return {
        messages: map,
        order,
        historyLoadedFor: s.currentSessionId,
        historyHasMoreBefore: page?.has_more_before ?? false,
        historyHasMoreAfter: page?.has_more_after ?? false,
      };
    }),

  prependHistory: (messages, page) =>
    set((s) => {
      const map = new Map(s.messages);
      const ids: string[] = [];
      for (const m of messages) {
        const exists = map.has(m.id);
        map.set(m.id, m);
        if (!exists) ids.push(m.id);
      }
      return {
        messages: map,
        order: [...ids, ...s.order],
        historyLoadedFor: s.currentSessionId,
        historyHasMoreBefore: page?.has_more_before ?? false,
        historyHasMoreAfter: s.historyHasMoreAfter || Boolean(page?.has_more_after),
      };
    }),

  appendHistoryPage: (messages, page) =>
    set((s) => {
      const map = new Map(s.messages);
      const ids: string[] = [];
      for (const m of messages) {
        const exists = map.has(m.id);
        map.set(m.id, m);
        if (!exists) ids.push(m.id);
      }
      return {
        messages: map,
        order: [...s.order, ...ids],
        historyLoadedFor: s.currentSessionId,
        historyHasMoreBefore: s.historyHasMoreBefore || Boolean(page?.has_more_before),
        historyHasMoreAfter: page?.has_more_after ?? false,
      };
    }),

  setHistoryLoading: (direction, loading) =>
    set(
      direction === "before"
        ? { historyLoadingBefore: loading }
        : { historyLoadingAfter: loading },
    ),

  appendMessage: (message) =>
    set((s) => {
      const messages = new Map(s.messages);
      messages.set(message.id, message);
      if (s.messages.has(message.id)) return { messages };
      return { messages, order: [...s.order, message.id] };
    }),

  insertMessageBefore: (message, beforeId) =>
    set((s) => {
      const messages = new Map(s.messages);
      messages.set(message.id, message);
      if (s.messages.has(message.id)) return { messages };

      const beforeIndex = beforeId ? s.order.indexOf(beforeId) : -1;
      if (beforeIndex < 0) return { messages, order: [...s.order, message.id] };

      const order = s.order.slice();
      order.splice(beforeIndex, 0, message.id);
      return { messages, order };
    }),

  mutateMessage: (id, patch) =>
    set((s) => {
      const existing = s.messages.get(id);
      if (!existing) return s;
      const messages = new Map(s.messages);
      messages.set(id, { ...existing, ...patch });
      return { messages };
    }),

  truncateFrom: (id) =>
    set((s) => {
      const idx = s.order.indexOf(id);
      if (idx < 0) {
        console.warn("[ntrp] truncateFrom: id not found in order", { id, order: s.order });
        return s;
      }
      const keep = s.order.slice(0, idx);
      const messages = new Map<string, UiMessage>();
      for (const k of keep) {
        const m = s.messages.get(k);
        if (m) messages.set(k, m);
      }
      return { messages, order: keep };
    }),

  setConnected: (connected) => set({ connected }),
  setRunning: (running) => set({ running }),
  setError: (error) => set({ error }),
  setDraft: (draft) => set({ draft }),
  setEditingId: (editingId) => set({ editingId }),
  resetUsage: () => set({ usage: initialUsage }),
  accumulateUsage: ({ prompt, completion, cost }) =>
    set((s) => ({
      usage: {
        lastPrompt: prompt,
        totalTokens: s.usage.totalTokens + prompt + completion,
        totalCost: s.usage.totalCost + cost,
      },
    })),

  openSettings: () =>
    set((s) => ({
      settingsOpen: true,
      connectionDraft: { ...s.config },
      connectionError: null,
    })),
  closeSettings: () =>
    set((s) => {
      if (s.connectionSaving) return s;
      return { settingsOpen: false, connectionError: null };
    }),
  setConnectionDraft: (patch) =>
    set((s) => ({ connectionDraft: { ...s.connectionDraft, ...patch } })),
  setConnectionError: (connectionError) => set({ connectionError }),
  setConnectionSaving: (connectionSaving) => set({ connectionSaving }),

  setActiveActivityId: (activeActivityId) => set({ activeActivityId }),

  appendActivityItem: (activityId, item) =>
    set((s) => {
      const existing = s.messages.get(activityId);
      if (!existing || !existing.activity) return s;
      const messages = new Map(s.messages);
      const activity = existing.activity;
      messages.set(activityId, {
        ...existing,
        activity: { ...activity, items: [...activity.items, item] },
      });
      return { messages };
    }),

  mergeActivityItem: (itemId, patch) =>
    set((s) => {
      // Tool results may arrive after the next activity has already opened —
      // scan all activity messages for the matching item id.
      let touched = false;
      const messages = new Map(s.messages);
      for (const [mid, msg] of messages) {
        if (!msg.activity) continue;
        const idx = msg.activity.items.findIndex((it) => it.id === itemId);
        if (idx < 0) continue;
        const items = msg.activity.items.slice();
        items[idx] = { ...items[idx], ...patch };
        messages.set(mid, { ...msg, activity: { ...msg.activity, items } });
        touched = true;
        break;
      }
      return touched ? { messages } : s;
    }),

  finalizeActivity: (activityId, label = "Called") =>
    set((s) => {
      const existing = s.messages.get(activityId);
      if (!existing || !existing.activity) return s;
      const messages = new Map(s.messages);
      messages.set(activityId, {
        ...existing,
        activity: { ...existing.activity, done: true, label },
      });
      return { messages };
    }),

  setCurrentRunId: (currentRunId) => set({ currentRunId }),
  setSkipApprovals: (skipApprovals) => set({ skipApprovals }),

  setApprovalStatus: (id, status) =>
    set((s) => {
      const existing = s.messages.get(id);
      if (!existing || !existing.approval) return s;
      const messages = new Map(s.messages);
      messages.set(id, { ...existing, approval: { ...existing.approval, status } });
      return { messages };
    }),

  setSkills: (skills) => set({ skills }),
  setCommandPickerOpen: (commandPickerOpen) => set({ commandPickerOpen, commandPickerIndex: 0 }),
  setCommandPickerIndex: (commandPickerIndex) => set({ commandPickerIndex }),
  setSelectedSkill: (selectedSkill) => set({ selectedSkill }),
  setViewingMarkdown: (viewingMarkdown) => set({ viewingMarkdown }),
  setViewingTool: (viewingTool) => set({ viewingTool }),

  addPendingImages: (images) =>
    set((s) => ({ pendingImages: [...s.pendingImages, ...images] })),
  removePendingImage: (index) =>
    set((s) => ({ pendingImages: s.pendingImages.filter((_, i) => i !== index) })),
  clearPendingImages: () => set({ pendingImages: [] }),

  setServerConfig: (serverConfig) => set({ serverConfig }),
  setServerModels: (serverModels) => set({ serverModels }),
  setAutomations: (automations) => set({ automations }),
  openAutomations: () => set({ automationsOpen: true }),
  closeAutomations: () => set({ automationsOpen: false }),
  setArchivedSessions: (archivedSessions) => set({ archivedSessions }),
  openArchive: () => set({ archiveOpen: true }),
  closeArchive: () => set({ archiveOpen: false }),
  setCompacting: (compacting) => set({ compacting }),
  setLastCompaction: (lastCompaction) => set({ lastCompaction }),
  openMemory: () => set({ memoryOpen: true }),
  closeMemory: () => set({ memoryOpen: false }),
  setSourceFocus: (sourceFocus) => set({ sourceFocus }),
  openPalette: () => set({ paletteOpen: true }),
  closePalette: () => set({ paletteOpen: false }),
  togglePalette: () => set((s) => ({ paletteOpen: !s.paletteOpen })),
  setPref: (key, value) =>
    set((s) => {
      const next = { ...s.prefs, [key]: value };
      persistPrefs(next);
      return { prefs: next };
    }),
  toggleSidebar: () =>
    set((s) => {
      const next = { ...s.prefs, sidebarHidden: !s.prefs.sidebarHidden };
      persistPrefs(next);
      return { prefs: next };
    }),
}));

// Helpers for use outside React (e.g. inside event-stream handlers).
export const getState = useStore.getState;
export const setState = useStore.setState;
