import { create } from "zustand";
import { DEFAULT_CONFIG } from "../api";
import type { State, Actions, UiMessage } from "./types";
import { loadPrefs, loadSkipApprovals, persistPrefs, persistSkipApprovals } from "./prefs";
import { blankSessionView, initialUsage, snapshotSession } from "./session-cache";

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
  ImageBlock,
  MarkdownViewState,
  PaletteId,
  Prefs,
  QueuedMessage,
  QueuedMessageStatus,
  Role,
  ServerLoop,
  SessionUsage,
  State,
  ThemeChoice,
  ThinkingAnimation,
  ThinkingIntensity,
  TurnMeta,
  UiMessage,
} from "./types";
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
      for (const agent of agents) {
        const key = `${sessionId}:${agent.taskId}`;
        const prev = next[key];
        next[key] = {
          taskId: agent.taskId,
          sessionId,
          command: agent.command,
          status: agent.status ?? prev?.status ?? "running",
          detail: agent.detail ?? prev?.detail,
          resultRef: agent.resultRef ?? prev?.resultRef,
          createdAt: prev?.createdAt ?? now,
          updatedAt: now,
        };
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
