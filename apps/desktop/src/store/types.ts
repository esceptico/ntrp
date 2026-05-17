import type {
  AppConfig,
  ArchivedSession,
  Automation,
  ModelsResponse,
  ServerConfig,
  SessionListItem,
  SkillDescriptor,
} from "../api";
import type { MessageSourceFocus } from "../lib/messageSourceFocus";
import type { AutomationStreamDomainState } from "./automation-domain";
import type { BackgroundAgentsDomainState } from "./background-agent-domain";
import type { SessionViewState } from "./session-view";

export type { SessionViewState } from "./session-view";

export type Role =
  | "user"
  | "assistant"
  | "reasoning"
  | "tool"
  | "status"
  | "error"
  | "activity"
  | "approval";

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

export interface GlassParams {
  /** Tint opacity 0–100 (% white for light mode; framework derives dark). */
  tint: number;
  /** Backdrop-filter blur in px. */
  blur: number;
  /** Backdrop-filter saturate %. */
  saturate: number;
  /** Top-edge specular rim opacity 0–100 (%). */
  rim: number;
}

export type GlassPrefs = GlassParams;

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
  glass: GlassPrefs;
}

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

export type BackgroundAgentStatus =
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "interrupted"
  | "cancel_requested";

export interface BackgroundAgent {
  taskId: string;
  sessionId: string;
  command: string;
  status: BackgroundAgentStatus;
  detail?: string;
  resultRef?: string;
  createdAt: number;
  updatedAt: number;
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
  /** Subagent token usage (only populated when `semanticKind === "agent"`).
   *  Reports the spawned agent's INTERNAL spend — these tokens never enter
   *  the parent's context. Used by the activity-trace agent row to surface
   *  per-agent context + cost without polluting the parent's budget gauge. */
  usage?: {
    prompt: number;
    completion: number;
    total: number;
    cache_read?: number;
    cache_write?: number;
  };
  /** Subagent USD cost (only populated when `semanticKind === "agent"`).
   *  Already rolled up into the parent run's `totalCost` server-side. */
  cost?: number;
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
  /** Server-side message count after the latest run. Drives the message
   *  scale on the budget dial. 0 before the first run finishes. */
  messageCount: number;
}

export interface MarkdownViewState {
  title: string;
  subtitle?: string;
  content: string;
  /** Optional filesystem path — surfaces an "open in OS" affordance. */
  sourcePath?: string;
}

/** Per-session view state cached across `setCurrentSession` switches.
 *  Snapshotted on switch-out, hydrated on switch-back, so flipping
 *  between sessions doesn't blank the UI while history reloads. The
 *  SSE replay (with the bus's checkpoint watermark) catches up any
 *  events that landed while the session was in the background. */
export interface CachedSessionState {
  sessionView: SessionViewState;
  messages: Map<string, UiMessage>;
  order: string[];
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
  pendingResume: { runId: string | null; sessionId: string } | null;
  stoppingRunId: string | null;
}

export interface State {
  config: AppConfig;
  sessions: SessionListItem[];
  sessionView: SessionViewState;
  currentSessionId: string | null;
  messages: Map<string, UiMessage>;
  order: string[];
  /** Session ids with an active run on the server. Refreshed by a
   *  poller hook so the sidebar can render a streaming indicator on
   *  sessions that are still working — including the ones the user
   *  isn't currently viewing. */
  activeRunSessionIds: Set<string>;
  /** Sessions whose runs finished while the user wasn't looking at
   *  them. Cleared when the user opens the session. Renders as an
   *  "unread" dot in the sidebar. */
  unreadDoneSessionIds: Set<string>;
  /** Per-session UI state preserved across `setCurrentSession` swaps. */
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
  automationStream: AutomationStreamDomainState;
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
  /** Messages submitted while a run was in flight. */
  queuedMessages: QueuedMessage[];
  /** Run resume requested by the UI but not yet reflected by stream state. */
  pendingResume: { runId: string | null; sessionId: string } | null;
  /** Active run currently being stopped by the user. */
  stoppingRunId: string | null;
  /** Terminal run ids seen locally. Prevents stale status polls from
   *  re-adding a run that the live stream already finished. */
  terminalRunIds: Set<string>;
  /** Center point of the element that triggered the currently-open modal.
   *  Null when the modal opens via keyboard / palette / non-positional path. */
  modalOrigin: { x: number; y: number } | null;
  loops: ServerLoop[];
  backgroundAgents: BackgroundAgentsDomainState;
  prefs: Prefs;
}

export interface Actions {
  setConfig: (config: AppConfig) => void;
  setSessions: (sessions: SessionListItem[]) => void;
  prependSession: (session: SessionListItem) => void;
  syncActiveRuns: (
    runs: { runId?: string | null; sessionId: string; status?: string | null }[],
  ) => void;
  markRunStarted: (runId: string | null, sessionId: string) => void;
  markRunCompleted: (runId: string | null, sessionId?: string | null) => void;
  setCurrentSession: (sessionId: string | null) => void;
  setHistory: (messages: UiMessage[], page?: import("../api").HistoryPage) => void;
  prependHistory: (messages: UiMessage[], page?: import("../api").HistoryPage) => void;
  appendHistoryPage: (messages: UiMessage[], page?: import("../api").HistoryPage) => void;
  setHistoryLoading: (direction: "before" | "after", loading: boolean) => void;
  appendMessage: (message: UiMessage) => void;
  insertMessageBefore: (message: UiMessage, beforeId: string | null) => void;
  mutateMessage: (id: string, patch: Partial<UiMessage>) => void;
  truncateFrom: (id: string) => void;
  setConnected: (connected: boolean) => void;
  setError: (error: string | null) => void;
  setDraft: (draft: string) => void;
  setEditingId: (id: string | null) => void;
  resetUsage: () => void;
  accumulateUsage: (usage: { prompt: number; completion: number; cost: number; messageCount?: number }) => void;
  /** Replace the budget-relevant fields without touching cumulative spend.
   *  Used when loading a session's persisted state — last prompt size and
   *  message count come from disk; cumulative cost/tokens start fresh
   *  for the session view (server doesn't persist running totals). */
  hydrateUsageSnapshot: (snapshot: { lastPrompt: number; messageCount: number }) => void;
  openSettings: (origin?: { x: number; y: number } | null) => void;
  closeSettings: () => void;
  setConnectionDraft: (patch: Partial<AppConfig>) => void;
  setConnectionError: (error: string | null) => void;
  setConnectionSaving: (saving: boolean) => void;
  setActiveActivityId: (id: string | null) => void;
  appendActivityItem: (activityId: string, item: ActivityItem) => void;
  mergeActivityItem: (itemId: string, patch: Partial<ActivityItem>) => boolean;
  finalizeActivity: (activityId: string, label?: string) => void;
  setSkipApprovals: (skip: boolean) => void;
  setApprovalStatus: (id: string, status: ApprovalStatus) => void;
  addPendingApproval: (approval: ApprovalState) => void;
  resolvePendingApproval: (toolId: string) => void;
  setReviewingApproval: (
    toolId: string | null,
    origin?: { x: number; y: number } | null,
  ) => void;
  addQueuedMessage: (message: QueuedMessage) => void;
  setQueuedMessageStatus: (clientId: string, status: QueuedMessageStatus) => void;
  removeQueuedMessage: (clientId: string) => void;
  clearQueuedMessages: () => void;
  resetCancellingQueuedMessages: () => void;
  setLoops: (loops: ServerLoop[]) => void;
  setBackgroundAgentsForSession: (
    sessionId: string,
    agents: {
      taskId: string;
      command: string;
      status?: BackgroundAgentStatus;
      detail?: string;
      resultRef?: string;
    }[],
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
  automationStreamConnecting: () => void;
  automationStreamConnected: () => void;
  automationStreamStale: () => void;
  automationStreamFailed: (error: string) => void;
  automationStreamIdle: () => void;
  automationProgress: (taskId: string, status: string) => void;
  automationFinished: (taskId: string) => void;
  backgroundAgentsRefreshStarted: () => void;
  backgroundAgentsRefreshFailed: (error: string) => void;
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
