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

/** A user message submitted while a run was already active. The server
 *  queues it into the active run's inject_queue and consumes it on the
 *  next agent step; until then it lives only on the client. */
export type QueuedMessageStatus = "pending" | "cancelling" | "sent" | "failed";

export interface QueuedMessage {
  clientId: string;
  text: string;
  images?: ImageBlock[];
  status: QueuedMessageStatus;
  enqueuedAt: number;
}

export interface ServerLoop {
  task_id: string;
  session_id: string;
  prompt: string;
  every: string;
  enabled: boolean;
  iteration_count: number;
  max_iterations: number | null;
  stop_when: string | null;
  max_age_days: number | null;
  created_at: string;
  next_run_at: string | null;
  last_run_at: string | null;
  last_result: string | null;
  running_since: string | null;
}

export type BackgroundAgentStatus = "running" | "completed" | "failed" | "cancelled";

export interface BackgroundAgent {
  taskId: string;
  sessionId: string;
  command: string;
  status: BackgroundAgentStatus;
  detail?: string;
  createdAt: number;
  updatedAt: number;
}

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
  /** Electron accelerator string for the global quick-capture window
   *  shortcut, e.g. "CommandOrControl+Shift+Space". Pushed to the main
   *  process via IPC; main re-registers on change. Empty string disables
   *  the shortcut entirely. */
  quickCaptureShortcut: string;
}

export const SIDEBAR_MIN_WIDTH = 200;
export const SIDEBAR_MAX_WIDTH = 380;
export const SIDEBAR_SNAP_POINTS = [220, 244, 280, 320] as const;
export const SIDEBAR_SNAP_THRESHOLD_PX = 12;

const PREFS_KEY = "ntrp.desktop.prefs";
const PREFS_VERSION = 2;
export const DEFAULT_QUICK_CAPTURE_SHORTCUT = "CommandOrControl+Shift+Space";
const DEFAULT_PREFS: Prefs = {
  thinkingAnimation: "comet",
  thinkingIntensity: "normal",
  theme: "system",
  palette: "graphite",
  sidebarHidden: false,
  sidebarWidth: 272,
  showReasoningInChat: true,
  quickCaptureShortcut: DEFAULT_QUICK_CAPTURE_SHORTCUT,
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

// Auto mode (skip approvals) is conceptually session state, not a Prefs
// field — but we persist it to localStorage so closing the app and
// reopening doesn't silently flip the user back into approval-required
// mode without warning. Stored separately from `prefs` so the migration
// surface stays narrow.
const SKIP_APPROVALS_KEY = "ntrp.desktop.skipApprovals";

function loadSkipApprovals(): boolean {
  try {
    return localStorage.getItem(SKIP_APPROVALS_KEY) === "true";
  } catch {
    return false;
  }
}

function persistSkipApprovals(value: boolean): void {
  try {
    localStorage.setItem(SKIP_APPROVALS_KEY, value ? "true" : "false");
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
  taskStatus?: "running" | "completed" | "failed" | "cancelled";
  progress?: string;
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
  /** True for system-generated user messages that should be hidden from
   *  the transcript UI but kept in conversation history for the model
   *  (e.g. loop tick prompts). Mirrors Claude Code's isMeta convention. */
  isMeta?: boolean;
}

export interface SessionUsage {
  lastPrompt: number;
  totalTokens: number;
  totalCost: number;
}

/** Per-session view state cached across `setCurrentSession` switches.
 *  Snapshotted on switch-out, hydrated on switch-back, so flipping
 *  between sessions doesn't blank the UI while history reloads. The
 *  SSE replay (with the bus's checkpoint watermark) catches up any
 *  events that landed while the session was in the background. */
export interface CachedSessionState {
  messages: Map<string, UiMessage>;
  order: string[];
  historyLoadedFor: string | null;
  historyHasMoreBefore: boolean;
  historyHasMoreAfter: boolean;
  historyLoadingBefore: boolean;
  historyLoadingAfter: boolean;
  running: boolean;
  currentRunId: string | null;
  usage: SessionUsage;
  editingId: string | null;
  activeActivityId: string | null;
  compacting: boolean;
  lastCompaction: { before: number; after: number; at: number } | null;
  sourceFocus: MessageSourceFocus | null;
  pendingApprovals: ApprovalState[];
  reviewingApprovalToolId: string | null;
  queuedMessages: QueuedMessage[];
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
  /** Per-session UI state preserved across `setCurrentSession` swaps.
   *  Outgoing session is snapshotted in, incoming is hydrated out.
   *  See `CachedSessionState`. */
  sessionCache: Map<string, CachedSessionState>;
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
  /** Live "current step" string per running automation, fed by the
   *  `/automations/events` SSE stream. Cleared on automation_finished. */
  automationStatuses: Record<string, string>;
  archiveOpen: boolean;
  archivedSessions: ArchivedSession[] | null;
  compacting: boolean;
  lastCompaction: { before: number; after: number; at: number } | null;
  memoryOpen: boolean;
  sourceFocus: MessageSourceFocus | null;
  paletteOpen: boolean;
  /** Tool approvals waiting on the user. Lives outside `messages` so the
   *  approval UI can render as its own surface (sticky banner above the
   *  composer) without interleaving with the agent's narrative trace. */
  pendingApprovals: ApprovalState[];
  /** When non-null, the approval UI is showing a diff/preview modal for
   *  this approval's `toolId`. */
  reviewingApprovalToolId: string | null;
  /** Messages submitted while a run was in flight. Server queues them
   *  into the active run's inject_queue; we mirror them here so the
   *  composer can show them as a stack of pending bubbles above the
   *  input until `message_ingested` arrives. */
  queuedMessages: QueuedMessage[];
  /** Center point of the element that triggered the currently-open
   *  modal (Settings, Automations, Archive, Memory, Approval review).
   *  Used as the spatial origin for the modal's open/close animation so
   *  the surface visibly grows from where it was summoned. Null when the
   *  modal opens via keyboard / palette / non-positional path — in that
   *  case the modal falls back to a neutral center fade. */
  modalOrigin: { x: number; y: number } | null;
  loops: ServerLoop[];
  backgroundAgents: Record<string, BackgroundAgent>;
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
  openSettings: (origin?: { x: number; y: number } | null) => void;
  closeSettings: () => void;
  setConnectionDraft: (patch: Partial<AppConfig>) => void;
  setConnectionError: (error: string | null) => void;
  setConnectionSaving: (saving: boolean) => void;
  setActiveActivityId: (id: string | null) => void;
  appendActivityItem: (activityId: string, item: ActivityItem) => void;
  mergeActivityItem: (itemId: string, patch: Partial<ActivityItem>) => boolean;
  finalizeActivity: (activityId: string, label?: string) => void;
  setCurrentRunId: (runId: string | null) => void;
  setSkipApprovals: (skip: boolean) => void;
  setApprovalStatus: (id: string, status: ApprovalStatus) => void;
  addPendingApproval: (approval: ApprovalState) => void;
  resolvePendingApproval: (toolId: string) => void;
  setReviewingApproval: (toolId: string | null, origin?: { x: number; y: number } | null) => void;
  addQueuedMessage: (message: QueuedMessage) => void;
  setQueuedMessageStatus: (clientId: string, status: QueuedMessageStatus) => void;
  removeQueuedMessage: (clientId: string) => void;
  clearQueuedMessages: () => void;
  resetCancellingQueuedMessages: () => void;
  setLoops: (loops: ServerLoop[]) => void;
  setBackgroundAgentsForSession: (
    sessionId: string,
    agents: { taskId: string; command: string }[],
  ) => void;
  upsertBackgroundAgent: (
    agent: Omit<BackgroundAgent, "createdAt"> & { createdAt?: number },
  ) => void;
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
  openAutomations: (origin?: { x: number; y: number } | null) => void;
  closeAutomations: () => void;
  setAutomationStatus: (taskId: string, status: string) => void;
  clearAutomationStatus: (taskId: string) => void;
  setArchivedSessions: (sessions: ArchivedSession[] | null) => void;
  openArchive: (origin?: { x: number; y: number } | null) => void;
  closeArchive: () => void;
  setCompacting: (compacting: boolean) => void;
  setLastCompaction: (info: State["lastCompaction"]) => void;
  openMemory: (origin?: { x: number; y: number } | null) => void;
  closeMemory: () => void;
  setSourceFocus: (focus: MessageSourceFocus | null) => void;
  openPalette: () => void;
  closePalette: () => void;
  togglePalette: () => void;
  setPref: <K extends keyof Prefs>(key: K, value: Prefs[K]) => void;
  toggleSidebar: () => void;
}

const initialUsage: SessionUsage = { lastPrompt: 0, totalTokens: 0, totalCost: 0 };

function blankSessionView(): CachedSessionState {
  return {
    messages: new Map(),
    order: [],
    historyLoadedFor: null,
    historyHasMoreBefore: false,
    historyHasMoreAfter: false,
    historyLoadingBefore: false,
    historyLoadingAfter: false,
    running: false,
    currentRunId: null,
    usage: initialUsage,
    editingId: null,
    activeActivityId: null,
    compacting: false,
    lastCompaction: null,
    sourceFocus: null,
    pendingApprovals: [],
    reviewingApprovalToolId: null,
    queuedMessages: [],
  };
}

function snapshotSession(s: State): CachedSessionState {
  return {
    messages: s.messages,
    order: s.order,
    historyLoadedFor: s.historyLoadedFor,
    historyHasMoreBefore: s.historyHasMoreBefore,
    historyHasMoreAfter: s.historyHasMoreAfter,
    historyLoadingBefore: s.historyLoadingBefore,
    historyLoadingAfter: s.historyLoadingAfter,
    running: s.running,
    currentRunId: s.currentRunId,
    usage: s.usage,
    editingId: s.editingId,
    activeActivityId: s.activeActivityId,
    compacting: s.compacting,
    lastCompaction: s.lastCompaction,
    sourceFocus: s.sourceFocus,
    pendingApprovals: s.pendingApprovals,
    reviewingApprovalToolId: s.reviewingApprovalToolId,
    queuedMessages: s.queuedMessages,
  };
}

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
  sessionCache: new Map(),
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
  skipApprovals: loadSkipApprovals(),
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
  automationStatuses: {},
  archiveOpen: false,
  archivedSessions: null,
  compacting: false,
  lastCompaction: null,
  memoryOpen: false,
  sourceFocus: null,
  paletteOpen: false,
  pendingApprovals: [],
  reviewingApprovalToolId: null,
  queuedMessages: [],
  modalOrigin: null,
  loops: [],
  backgroundAgents: {},
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
      // Re-selecting the same session is a no-op for view state — the
      // global slots ARE that session's live state. Touching cache here
      // would clobber it with a stale snapshot.
      if (s.currentSessionId === currentSessionId) {
        return unread !== s.unreadDoneSessionIds ? { unreadDoneSessionIds: unread } : {};
      }
      // Snapshot outgoing session into cache so a switch-back can
      // restore the UI instantly and the SSE replay (with the bus
      // checkpoint watermark) only fills in what's new.
      const cache = new Map(s.sessionCache);
      if (s.currentSessionId) {
        cache.set(s.currentSessionId, snapshotSession(s));
      }
      const restored = currentSessionId ? cache.get(currentSessionId) : undefined;
      const view = restored ?? blankSessionView();
      return {
        currentSessionId,
        sessionCache: cache,
        messages: view.messages,
        order: view.order,
        usage: view.usage,
        editingId: view.editingId,
        activeActivityId: view.activeActivityId,
        currentRunId: view.currentRunId,
        running: view.running,
        compacting: view.compacting,
        lastCompaction: view.lastCompaction,
        sourceFocus: view.sourceFocus,
        historyLoadedFor: view.historyLoadedFor,
        historyHasMoreBefore: view.historyHasMoreBefore,
        historyHasMoreAfter: view.historyHasMoreAfter,
        historyLoadingBefore: view.historyLoadingBefore,
        historyLoadingAfter: view.historyLoadingAfter,
        pendingApprovals: view.pendingApprovals,
        reviewingApprovalToolId: view.reviewingApprovalToolId,
        queuedMessages: view.queuedMessages,
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
      const persistedIds = new Set(order);
      return {
        messages: map,
        order,
        historyLoadedFor: s.currentSessionId,
        historyHasMoreBefore: page?.has_more_before ?? false,
        historyHasMoreAfter: page?.has_more_after ?? false,
        queuedMessages: s.queuedMessages.filter((q) => !persistedIds.has(q.clientId)),
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

  openSettings: (origin) =>
    set((s) => ({
      settingsOpen: true,
      connectionDraft: { ...s.config },
      connectionError: null,
      modalOrigin: origin ?? null,
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

  mergeActivityItem: (itemId, patch) => {
    let didTouch = false;
    set((s) => {
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
      didTouch = touched;
      return touched ? { messages } : s;
    });
    return didTouch;
  },

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
  setSkipApprovals: (skipApprovals) => {
    persistSkipApprovals(skipApprovals);
    set({ skipApprovals });
  },

  setApprovalStatus: (id, status) =>
    set((s) => {
      const existing = s.messages.get(id);
      if (!existing || !existing.approval) return s;
      const messages = new Map(s.messages);
      messages.set(id, { ...existing, approval: { ...existing.approval, status } });
      return { messages };
    }),

  addPendingApproval: (approval) =>
    set((s) => {
      // Dedupe by toolId — same tool re-emitting approval shouldn't stack.
      const filtered = s.pendingApprovals.filter((a) => a.toolId !== approval.toolId);
      return { pendingApprovals: [...filtered, approval] };
    }),
  resolvePendingApproval: (toolId) =>
    set((s) => ({
      pendingApprovals: s.pendingApprovals.filter((a) => a.toolId !== toolId),
      reviewingApprovalToolId:
        s.reviewingApprovalToolId === toolId ? null : s.reviewingApprovalToolId,
    })),
  setReviewingApproval: (toolId, origin) =>
    set({ reviewingApprovalToolId: toolId, modalOrigin: toolId ? origin ?? null : null }),

  addQueuedMessage: (message) =>
    set((s) => ({ queuedMessages: [...s.queuedMessages, message] })),
  setQueuedMessageStatus: (clientId, status) =>
    set((s) => ({
      queuedMessages: s.queuedMessages.map((q) =>
        q.clientId === clientId ? { ...q, status } : q,
      ),
    })),
  removeQueuedMessage: (clientId) =>
    set((s) => ({
      queuedMessages: s.queuedMessages.filter((q) => q.clientId !== clientId),
    })),
  clearQueuedMessages: () => set({ queuedMessages: [] }),
  // After a run terminates without ingesting a queued message, the
  // server dropped its inject_queue. Any "cancelling" entries are now
  // stuck — flip them back to "pending" so the user can retry/cancel.
  resetCancellingQueuedMessages: () =>
    set((s) => ({
      queuedMessages: s.queuedMessages.map((q) =>
        q.status === "cancelling" ? { ...q, status: "pending" } : q,
      ),
    })),
  setLoops: (loops) => set({ loops }),
  setBackgroundAgentsForSession: (sessionId, agents) =>
    set((s) => {
      const now = Date.now();
      const next = { ...(s.backgroundAgents ?? {}) };
      const seen = new Set<string>();
      for (const agent of agents) {
        const key = `${sessionId}:${agent.taskId}`;
        seen.add(key);
        const prev = next[key];
        next[key] = {
          taskId: agent.taskId,
          sessionId,
          command: agent.command,
          status: prev?.status ?? "running",
          detail: prev?.detail,
          createdAt: prev?.createdAt ?? now,
          updatedAt: now,
        };
      }
      for (const [key, agent] of Object.entries(next)) {
        if (agent.sessionId === sessionId && !seen.has(key) && agent.status === "running") {
          next[key] = { ...agent, status: "completed", updatedAt: now };
        }
      }
      return { backgroundAgents: next };
    }),
  upsertBackgroundAgent: (agent) =>
    set((s) => {
      const now = Date.now();
      const key = `${agent.sessionId}:${agent.taskId}`;
      const prev = (s.backgroundAgents ?? {})[key];
      return {
        backgroundAgents: {
          ...(s.backgroundAgents ?? {}),
          [key]: {
            ...prev,
            ...agent,
            createdAt: agent.createdAt ?? prev?.createdAt ?? now,
            updatedAt: agent.updatedAt ?? now,
          },
        },
      };
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
  openAutomations: (origin) => set({ automationsOpen: true, modalOrigin: origin ?? null }),
  closeAutomations: () => set({ automationsOpen: false }),
  setAutomationStatus: (taskId, status) =>
    set((s) => ({ automationStatuses: { ...s.automationStatuses, [taskId]: status } })),
  clearAutomationStatus: (taskId) =>
    set((s) => {
      if (!(taskId in s.automationStatuses)) return s;
      const next = { ...s.automationStatuses };
      delete next[taskId];
      return { automationStatuses: next };
    }),
  setArchivedSessions: (archivedSessions) => set({ archivedSessions }),
  openArchive: (origin) => set({ archiveOpen: true, modalOrigin: origin ?? null }),
  closeArchive: () => set({ archiveOpen: false }),
  setCompacting: (compacting) => set({ compacting }),
  setLastCompaction: (lastCompaction) => set({ lastCompaction }),
  openMemory: (origin) => set({ memoryOpen: true, modalOrigin: origin ?? null }),
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
