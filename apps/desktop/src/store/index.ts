import { create } from "zustand";
import { DEFAULT_CONFIG } from "../api";
import type { State, Actions, UiMessage } from "./types";
import { loadPrefs, loadSkipApprovals, persistPrefs, persistSkipApprovals } from "./prefs";
import { blankSessionView, initialUsage, snapshotSession } from "./session-cache";
import {
  createInitialSessionViewState,
  reduceCachePreviewRestored,
  reduceHistoryLoadSucceeded,
  reduceHistoryPageLoading,
  reduceSessionSelected,
} from "./session-view";
import {
  createAutomationStreamDomainState,
  reduceAutomationFinished,
  reduceAutomationProgress,
  reduceAutomationStreamConnected,
  reduceAutomationStreamConnecting,
  reduceAutomationStreamFailed,
  reduceAutomationStreamIdle,
  reduceAutomationStreamStale,
  type AutomationStreamDomainState,
  type AutomationStreamPhase,
} from "./automation-domain";
import {
  createBackgroundAgentsDomainState,
  reduceBackgroundAgentUpsert,
  reduceBackgroundAgentsForSession,
  reduceBackgroundAgentsRefreshFailed,
  reduceBackgroundAgentsRefreshStarted,
  type BackgroundAgentsDomainState,
  type BackgroundAgentRefreshStatus,
} from "./background-agent-domain";
import {
  reduceApprovalRequested,
  reduceApprovalResolved,
  reduceCancellingQueuedMessagesReset,
  reduceQueuedMessageAdded,
  reduceQueuedMessageRemoved,
  reduceQueuedMessagesCleared,
  reduceQueuedMessagesPersisted,
  reduceQueuedMessageStatus,
  reduceRunCompleted,
  reduceRunStarted,
  reduceRunStatus,
} from "./run-lifecycle";

// Re-export types so existing `import { X } from "../store"` keeps working.
export type {
  ActivityItem,
  ActivityState,
  Actions,
  ApprovalState,
  ApprovalStatus,
  BackgroundAgent,
  BackgroundAgentStatus,
  CachedSessionState,
  GlassParams,
  GlassPrefs,
  ImageBlock,
  MarkdownViewState,
  Material,
  PaletteId,
  Prefs,
  QueuedMessage,
  QueuedMessageStatus,
  Role,
  ServerLoop,
  SessionUsage,
  SessionViewState,
  State,
  ThemeChoice,
  ThinkingAnimation,
  ThinkingIntensity,
  TurnMeta,
  UiMessage,
} from "./types";
export type {
  AutomationStreamPhase,
  BackgroundAgentRefreshStatus,
  BackgroundAgentsDomainState,
  AutomationStreamDomainState,
};
export {
  DEFAULT_QUICK_CAPTURE_SHORTCUT,
  SIDEBAR_MAX_WIDTH,
  SIDEBAR_MIN_WIDTH,
  SIDEBAR_SNAP_POINTS,
  SIDEBAR_SNAP_THRESHOLD_PX,
} from "./prefs";

export const useStore = create<State & Actions>((set) => ({
  config: { ...DEFAULT_CONFIG },
  sessions: [],
  sessionView: createInitialSessionViewState(),
  currentSessionId: null,
  messages: new Map(),
  order: [],
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
  automationStream: createAutomationStreamDomainState(),
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
  pendingResume: null,
  stoppingRunId: null,
  terminalRunIds: new Set(),
  modalOrigin: null,
  loops: [],
  backgroundAgents: createBackgroundAgentsDomainState(),
  goals: {},
  prefs: loadPrefs(),

  setConfig: (config) => set({ config, connectionDraft: { ...config } }),
  setSessions: (sessions) => set({ sessions }),
  prependSession: (session) => set((s) => ({ sessions: [session, ...s.sessions] })),
  syncActiveRuns: (runs) => set((s) => reduceRunStatus(s, { activeRuns: runs })),
  markRunStarted: (runId, sessionId) =>
    set((s) => reduceRunStarted(s, { runId, sessionId })),
  markRunCompleted: (runId, sessionId) =>
    set((s) => reduceRunCompleted(s, { runId, sessionId })),
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
      let sessionView = reduceSessionSelected(s.sessionView, currentSessionId);
      if (currentSessionId && restored) {
        sessionView = reduceCachePreviewRestored(sessionView, currentSessionId);
      }
      return {
        sessionView,
        currentSessionId: sessionView.currentSessionId,
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
        pendingApprovals: view.pendingApprovals,
        reviewingApprovalToolId: view.reviewingApprovalToolId,
        queuedMessages: view.queuedMessages,
        pendingResume: view.pendingResume,
        stoppingRunId: view.stoppingRunId,
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
      const sessionView = s.currentSessionId
        ? reduceHistoryLoadSucceeded(s.sessionView, s.currentSessionId, page)
        : s.sessionView;
      return {
        sessionView,
        messages: map,
        order,
        ...reduceQueuedMessagesPersisted(s, persistedIds),
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
      const sessionView = s.currentSessionId
        ? reduceHistoryLoadSucceeded(s.sessionView, s.currentSessionId, page, "prepend")
        : s.sessionView;
      return {
        sessionView,
        messages: map,
        order: [...ids, ...s.order],
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
      const sessionView = s.currentSessionId
        ? reduceHistoryLoadSucceeded(s.sessionView, s.currentSessionId, page, "append")
        : s.sessionView;
      return {
        sessionView,
        messages: map,
        order: [...s.order, ...ids],
      };
    }),

  setHistoryLoading: (direction, loading) =>
    set((s) => {
      const sessionView = reduceHistoryPageLoading(s.sessionView, direction, loading);
      return { sessionView };
    }),

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
  setError: (error) => set({ error }),
  setDraft: (draft) => set({ draft }),
  setEditingId: (editingId) => set({ editingId }),
  resetUsage: () => set({ usage: initialUsage }),
  accumulateUsage: ({ prompt, completion, cost, messageCount }) =>
    set((s) => ({
      usage: {
        lastPrompt: prompt,
        totalTokens: s.usage.totalTokens + prompt + completion,
        totalCost: s.usage.totalCost + cost,
        messageCount: messageCount ?? s.usage.messageCount,
      },
    })),
  hydrateUsageSnapshot: ({ lastPrompt, messageCount }) =>
    set((s) => ({
      usage: { ...s.usage, lastPrompt, messageCount },
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

  addPendingApproval: (approval) => set((s) => reduceApprovalRequested(s, approval)),
  resolvePendingApproval: (toolId) => set((s) => reduceApprovalResolved(s, toolId)),
  setReviewingApproval: (toolId, origin) =>
    set({ reviewingApprovalToolId: toolId, modalOrigin: toolId ? origin ?? null : null }),

  addQueuedMessage: (message) => set((s) => reduceQueuedMessageAdded(s, message)),
  setQueuedMessageStatus: (clientId, status) =>
    set((s) => reduceQueuedMessageStatus(s, clientId, status)),
  removeQueuedMessage: (clientId) =>
    set((s) => reduceQueuedMessageRemoved(s, clientId)),
  clearQueuedMessages: () => set(reduceQueuedMessagesCleared()),
  // After a run terminates without ingesting a queued message, the
  // server dropped its inject_queue. Any "cancelling" entries are now
  // stuck — flip them back to "pending" so the user can retry/cancel.
  resetCancellingQueuedMessages: () =>
    set((s) => reduceCancellingQueuedMessagesReset(s)),
  setLoops: (loops) => set({ loops }),
  backgroundAgentsRefreshStarted: () =>
    set((s) => ({
      backgroundAgents: reduceBackgroundAgentsRefreshStarted(s.backgroundAgents),
    })),
  backgroundAgentsRefreshFailed: (error) =>
    set((s) => ({
      backgroundAgents: reduceBackgroundAgentsRefreshFailed(
        s.backgroundAgents,
        error,
      ),
    })),
  setBackgroundAgentsForSession: (sessionId, agents) =>
    set((s) => ({
      backgroundAgents: reduceBackgroundAgentsForSession(
        s.backgroundAgents,
        sessionId,
        agents,
      ),
    })),
  upsertBackgroundAgent: (agent) =>
    set((s) => ({
      backgroundAgents: reduceBackgroundAgentUpsert(s.backgroundAgents, agent),
    })),
  setGoal: (sessionId, goal) =>
    set((s) => {
      const goals = { ...s.goals };
      if (goal) goals[sessionId] = goal;
      else delete goals[sessionId];
      return { goals };
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
  automationStreamConnecting: () =>
    set((s) => ({
      automationStream: reduceAutomationStreamConnecting(s.automationStream),
    })),
  automationStreamConnected: () =>
    set((s) => ({
      automationStream: reduceAutomationStreamConnected(s.automationStream),
    })),
  automationStreamStale: () =>
    set((s) => ({
      automationStream: reduceAutomationStreamStale(s.automationStream),
    })),
  automationStreamFailed: (error) =>
    set((s) => ({
      automationStream: reduceAutomationStreamFailed(s.automationStream, error),
    })),
  automationStreamIdle: () =>
    set((s) => ({
      automationStream: reduceAutomationStreamIdle(s.automationStream),
    })),
  automationProgress: (taskId, status) =>
    set((s) => ({
      automationStream: reduceAutomationProgress(s.automationStream, taskId, status),
    })),
  automationFinished: (taskId) =>
    set((s) => ({
      automationStream: reduceAutomationFinished(s.automationStream, taskId),
    })),
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
