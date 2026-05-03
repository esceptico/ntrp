import "./styles.css";
import { marked } from "marked";
import DOMPurify from "dompurify";

marked.setOptions({ gfm: true, breaks: true });

function renderMarkdown(content: string): string {
  if (!content) return "";
  const html = marked.parse(content, { async: false }) as string;
  return DOMPurify.sanitize(html, {
    ADD_ATTR: ["target", "rel"],
    FORBID_TAGS: ["style", "iframe", "form", "input", "button"],
  });
}

type Role = "user" | "assistant" | "tool" | "reasoning" | "status" | "error";

interface AppConfig {
  serverUrl: string;
  apiKey: string;
}

interface SessionListItem {
  session_id: string;
  started_at: string;
  last_activity: string;
  name: string | null;
  message_count: number;
}

interface HistoryMessage {
  role: "user" | "assistant" | "tool";
  content: string;
  reasoning_content?: string;
}

interface HealthCheck {
  ok: boolean;
  version: string | null;
  hasProviders: boolean;
}

interface ApiBridgeResponse {
  ok: boolean;
  status: number;
  statusText: string;
  contentType: string;
  data: unknown;
  text: string;
}

interface UiMessage {
  id: string;
  role: Role;
  title?: string;
  subtitle?: string;
  content: string;
}

type ServerEvent =
  | { type: "text"; content: string }
  | { type: "text_delta"; content: string }
  | { type: "REASONING_MESSAGE_START"; messageId: string }
  | { type: "REASONING_MESSAGE_CONTENT"; messageId: string; delta: string }
  | { type: "tool_call"; tool_id: string; name: string; description?: string }
  | { type: "tool_result"; tool_id: string; name: string; preview?: string; result?: string }
  | { type: "run_started"; run_id: string; session_id: string; session_name?: string | null }
  | { type: "run_finished"; run_id: string; usage?: { prompt: number; completion: number; cache_read: number; cost: number } }
  | { type: "run_error"; message: string }
  | { type: "background_task"; command: string; status: string; detail?: string };

const STORAGE_KEY = "ntrp.desktop.config";
const DEFAULT_CONFIG: AppConfig = {
  serverUrl: "http://localhost:6877",
  apiKey: "",
};

interface SessionUsage {
  lastPrompt: number;
  totalTokens: number;
  totalCost: number;
}

const state: {
  config: AppConfig;
  sessions: SessionListItem[];
  currentSessionId: string | null;
  messages: UiMessage[];
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
  eventDisconnect?: () => void;
} = {
  config: { ...DEFAULT_CONFIG },
  sessions: [],
  currentSessionId: null,
  messages: [],
  connected: false,
  running: false,
  error: null,
  draft: "",
  settingsOpen: false,
  connectionDraft: { ...DEFAULT_CONFIG },
  connectionError: null,
  connectionSaving: false,
  usage: { lastPrompt: 0, totalTokens: 0, totalCost: 0 },
  editingId: null,
};

function getAppRoot(): HTMLDivElement {
  const element = document.querySelector<HTMLDivElement>("#app");
  if (!element) throw new Error("Missing #app");
  return element;
}

const appRoot = getAppRoot();

function loadLegacyConfig(): AppConfig {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return { ...DEFAULT_CONFIG };
  try {
    return normalizeConfig(JSON.parse(raw));
  } catch {
    return { ...DEFAULT_CONFIG };
  }
}

function normalizeConfig(config: Partial<AppConfig> | null | undefined): AppConfig {
  return {
    serverUrl: config?.serverUrl?.trim().replace(/\/$/, "") || DEFAULT_CONFIG.serverUrl,
    apiKey: config?.apiKey?.trim() ?? "",
  };
}

async function loadInitialConfig(): Promise<AppConfig> {
  const desktopConfig = window.ntrpDesktop?.config;
  if (!desktopConfig) return loadLegacyConfig();

  const config = await desktopConfig.get();
  if (config.apiKey || localStorage.getItem(STORAGE_KEY) === null) return normalizeConfig(config);

  const legacy = loadLegacyConfig();
  if (legacy.apiKey || legacy.serverUrl !== DEFAULT_CONFIG.serverUrl) {
    localStorage.removeItem(STORAGE_KEY);
    return desktopConfig.set(legacy);
  }
  return normalizeConfig(config);
}

async function saveConfig(config: AppConfig) {
  const normalized = normalizeConfig(config);
  state.config = window.ntrpDesktop?.config ? await window.ntrpDesktop.config.set(normalized) : normalized;
  state.connectionDraft = { ...state.config };
  localStorage.removeItem(STORAGE_KEY);
}

function headersForConfig(config: AppConfig, json = false): HeadersInit {
  const output: Record<string, string> = {};
  if (json) output["Content-Type"] = "application/json";
  if (config.apiKey) output.Authorization = `Bearer ${config.apiKey}`;
  return output;
}

function headers(json = false): HeadersInit {
  return headersForConfig(state.config, json);
}

function errorMessageFromResponse(response: { status: number; data?: unknown; text?: string }) {
  let message = `HTTP ${response.status}`;
  if (response.data && typeof response.data === "object") {
    const body = response.data as { detail?: unknown; message?: unknown };
    if (typeof body.detail === "string") message = body.detail;
    if (typeof body.message === "string") message = body.message;
  } else if (response.text) {
    message = response.text;
  }
  return message;
}

async function apiWithConfig<T>(config: AppConfig, path: string, init: RequestInit = {}): Promise<T> {
  const { timeout, ...requestInit } = init as RequestInit & { timeout?: number };
  const body = typeof requestInit.body === "string" ? requestInit.body : undefined;
  const desktopApi = window.ntrpDesktop?.api;
  if (desktopApi) {
    const response: ApiBridgeResponse = await desktopApi.request(config, {
      path,
      method: requestInit.method ?? "GET",
      body,
      timeout,
    });
    if (!response.ok) throw new Error(errorMessageFromResponse(response));
    return response.contentType.includes("application/json") ? (response.data as T) : (undefined as T);
  }

  const controller = new AbortController();
  const timeoutId = timeout && timeout > 0 ? window.setTimeout(() => controller.abort(), timeout) : null;
  const signal = requestInit.signal ? AbortSignal.any([controller.signal, requestInit.signal]) : controller.signal;

  try {
    const response = await fetch(`${config.serverUrl}${path}`, {
      ...requestInit,
      headers: {
        ...headersForConfig(config, Boolean(requestInit.body)),
        ...(requestInit.headers ?? {}),
      },
      signal,
    });

    if (!response.ok) {
      let data: unknown = null;
      let text = "";
      try {
        data = await response.json();
      } catch {
        text = await response.text();
      }
      throw new Error(errorMessageFromResponse({ status: response.status, data, text }));
    }

    if (!response.headers.get("content-type")?.includes("application/json")) {
      return undefined as T;
    }
    return response.json() as Promise<T>;
  } finally {
    if (timeoutId) window.clearTimeout(timeoutId);
  }
}

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  return apiWithConfig<T>(state.config, path, init);
}

async function checkHealth(config: AppConfig): Promise<HealthCheck> {
  try {
    const health = await apiWithConfig<{
      auth?: boolean;
      version?: string;
      has_providers?: boolean;
    }>(config, "/health", { timeout: 5000 } as RequestInit & { timeout: number });
    return {
      ok: health.auth !== false,
      version: health.version ?? null,
      hasProviders: health.has_providers ?? true,
    };
  } catch {
    return { ok: false, version: null, hasProviders: true };
  }
}

async function validateConnection(config: AppConfig): Promise<HealthCheck> {
  const normalized = normalizeConfig(config);
  if (!normalized.apiKey) throw new Error("API key is required");
  const health = await checkHealth(normalized);
  if (!health.ok) {
    throw new Error(health.version ? "Invalid API key" : "Could not reach ntrp server");
  }
  return health;
}

async function refresh() {
  try {
    const health = await checkHealth(state.config);
    if (!health.ok) {
      throw new Error(health.version ? "Invalid API key" : "Could not reach ntrp server");
    }
    state.connected = true;
    state.error = null;
    const [{ sessions }, session] = await Promise.all([
      api<{ sessions: SessionListItem[] }>("/sessions"),
      api<{ session_id: string; name?: string | null }>("/session"),
    ]);
    state.sessions = sessions;
    state.currentSessionId = session.session_id;
    await loadHistory(session.session_id);
    connectEvents(session.session_id);
  } catch (error) {
    state.connected = false;
    state.error = error instanceof Error ? error.message : String(error);
  }
  render();
}

async function loadHistory(sessionId: string) {
  const { messages } = await api<{ messages: HistoryMessage[] }>(`/session/history?session_id=${encodeURIComponent(sessionId)}`);
  state.messages = messages.flatMap((message, index) => {
    const items: UiMessage[] = [];
    if (message.reasoning_content) {
      items.push({
        id: `history-${index}-reasoning`,
        role: "reasoning",
        title: "Reasoning",
        content: message.reasoning_content,
      });
    }
    items.push({
      id: `history-${index}`,
      role: message.role,
      content: message.content,
    });
    return items;
  });
}

function connectEvents(sessionId: string) {
  state.eventDisconnect?.();

  const desktopEvents = window.ntrpDesktop?.events;
  if (desktopEvents) {
    let closed = false;
    let connectionId: string | null = null;
    const dispose = desktopEvents.onData(payload => {
      if (!connectionId || payload.connectionId !== connectionId) return;
      if (payload.error) {
        state.error = payload.error;
        render();
        return;
      }
      if (payload.event) handleEvent(payload.event as ServerEvent);
    });

    state.eventDisconnect = () => {
      closed = true;
      dispose();
      if (connectionId) void desktopEvents.disconnect(connectionId);
    };

    void desktopEvents.connect(state.config, sessionId).then(id => {
      if (closed) {
        void desktopEvents.disconnect(id);
        return;
      }
      connectionId = id;
    }).catch(error => {
      dispose();
      if (!closed) {
        state.error = error instanceof Error ? error.message : String(error);
        render();
      }
    });
    return;
  }

  const controller = new AbortController();
  state.eventDisconnect = () => controller.abort();

  void (async () => {
    while (!controller.signal.aborted) {
      try {
        const response = await fetch(`${state.config.serverUrl}/chat/events/${encodeURIComponent(sessionId)}?stream=true`, {
          headers: headers(),
          signal: controller.signal,
        });
        if (!response.ok || !response.body) throw new Error(`event stream failed: ${response.status}`);

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (!controller.signal.aborted) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";
          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            try {
              handleEvent(JSON.parse(line.slice(6)) as ServerEvent);
            } catch {
              // Ignore non-JSON keepalive events.
            }
          }
        }
      } catch (error) {
        if (controller.signal.aborted) return;
        state.error = error instanceof Error ? error.message : String(error);
        render();
        await new Promise(resolve => setTimeout(resolve, 1500));
      }
    }
  })();
}

function isAtBottom(el: Element, threshold = 64): boolean {
  return el.scrollTop + el.clientHeight >= el.scrollHeight - threshold;
}

function appendMessage(message: UiMessage) {
  state.messages.push(message);
  renderMessages();
}

function appendToLast(role: Role, delta: string, title?: string) {
  const last = state.messages.at(-1);
  if (last?.role === role && last.title === title) {
    last.content += delta;
    scheduleMessageUpdate(last.id);
    return;
  }
  appendMessage({ id: crypto.randomUUID(), role, title, content: delta });
}

const pendingMessageUpdates = new Set<string>();
let updateRaf: number | null = null;

function scheduleMessageUpdate(messageId: string) {
  pendingMessageUpdates.add(messageId);
  if (updateRaf !== null) return;
  updateRaf = requestAnimationFrame(() => {
    updateRaf = null;
    const ids = [...pendingMessageUpdates];
    pendingMessageUpdates.clear();

    const messagesEl = document.querySelector<HTMLElement>(".messages");
    const stuck = messagesEl ? isAtBottom(messagesEl) : true;

    for (const id of ids) {
      const message = state.messages.find(item => item.id === id);
      if (!message) continue;
      const article = document.querySelector<HTMLElement>(`article[data-id="${cssEscape(id)}"]`);
      if (!article) {
        renderMessages();
        return;
      }
      const body = article.querySelector<HTMLElement>(".message-body");
      if (body) body.innerHTML = renderMessageBodyHtml(message);
    }

    if (stuck && messagesEl) messagesEl.scrollTop = messagesEl.scrollHeight;
  });
}

function cssEscape(value: string): string {
  if (typeof CSS !== "undefined" && typeof CSS.escape === "function") return CSS.escape(value);
  return value.replace(/["\\]/g, "\\$&");
}

function renderMessages() {
  const inner = document.querySelector<HTMLElement>(".messages-inner");
  if (!inner) {
    render();
    return;
  }
  const messagesEl = inner.parentElement;
  const stuck = messagesEl ? isAtBottom(messagesEl) : true;
  inner.innerHTML = state.messages.length === 0
    ? renderEmptyState(state.connected)
    : state.messages.map(renderMessage).join("");
  if (stuck && messagesEl) messagesEl.scrollTop = messagesEl.scrollHeight;
}

function renderRunChip() {
  const chip = document.querySelector<HTMLElement>(".run-chip");
  if (chip) {
    chip.classList.toggle("running", state.running);
    chip.classList.toggle("idle", !state.running);
    chip.innerHTML = `<span class="pulse-dot"></span>${state.running ? "running" : "idle"}`;
  }
  const send = document.querySelector<HTMLButtonElement>("#composer-send");
  if (send) send.disabled = state.running || !state.connected || state.draft.trim().length === 0;
}

function formatTokens(n: number): string {
  if (n < 1000) return `${n}`;
  if (n < 10000) return `${(n / 1000).toFixed(1)}k`;
  return `${Math.round(n / 1000)}k`;
}

function formatCost(n: number): string {
  if (n < 0.01) return `$${n.toFixed(4)}`;
  return `$${n.toFixed(3)}`;
}

function usageText(): string {
  const { lastPrompt, totalCost } = state.usage;
  if (!lastPrompt && !totalCost) return "";
  const parts: string[] = [];
  if (lastPrompt) parts.push(`<strong>${formatTokens(lastPrompt)}</strong> ctx`);
  if (totalCost) parts.push(formatCost(totalCost));
  return parts.join(" · ");
}

function renderUsage() {
  const el = document.querySelector<HTMLElement>(".composer-usage");
  if (el) el.innerHTML = usageText();
}

async function copyMessage(messageId: string, button: HTMLElement) {
  const message = state.messages.find(item => item.id === messageId);
  if (!message) return;
  try {
    await navigator.clipboard.writeText(message.content);
    button.classList.add("copied");
    button.innerHTML = ICONS.check;
    setTimeout(() => {
      button.classList.remove("copied");
      button.innerHTML = ICONS.copy;
    }, 1200);
  } catch {
    // ignore
  }
}

function editMessage(messageId: string) {
  const message = state.messages.find(item => item.id === messageId);
  if (!message) return;
  state.editingId = messageId;
  const input = document.querySelector<HTMLTextAreaElement>("#message-input");
  if (!input) return;
  input.value = message.content;
  state.draft = message.content;
  resizeComposer(input);
  input.focus();
  input.setSelectionRange(message.content.length, message.content.length);
  const send = document.querySelector<HTMLButtonElement>("#composer-send");
  if (send) send.disabled = state.running || !state.connected || state.draft.trim().length === 0;
}

function handleEvent(event: ServerEvent) {
  if (event.type === "run_started") {
    state.running = true;
    state.error = null;
    renderRunChip();
    return;
  }
  if (event.type === "run_finished") {
    state.running = false;
    const usage = event.usage;
    if (usage) {
      state.usage = {
        lastPrompt: usage.prompt,
        totalTokens: state.usage.totalTokens + usage.prompt + usage.completion,
        totalCost: state.usage.totalCost + usage.cost,
      };
    }
    renderMessages();
    renderRunChip();
    renderUsage();
    return;
  }
  if (event.type === "run_error") {
    state.running = false;
    appendMessage({ id: crypto.randomUUID(), role: "error", content: event.message });
    renderRunChip();
    return;
  }
  if (event.type === "text" || event.type === "text_delta") {
    appendToLast("assistant", event.content);
    return;
  }
  if (event.type === "REASONING_MESSAGE_START") {
    appendMessage({ id: event.messageId, role: "reasoning", title: "Reasoning", content: "" });
    return;
  }
  if (event.type === "REASONING_MESSAGE_CONTENT") {
    const message = state.messages.find(item => item.id === event.messageId);
    if (message) {
      message.content += event.delta;
      scheduleMessageUpdate(message.id);
    } else {
      appendMessage({ id: event.messageId, role: "reasoning", title: "Reasoning", content: event.delta });
    }
    return;
  }
  if (event.type === "tool_call") {
    appendMessage({
      id: event.tool_id,
      role: "tool",
      title: event.name,
      subtitle: event.description || "",
      content: "",
    });
    return;
  }
  if (event.type === "tool_result") {
    const message = state.messages.find(item => item.id === event.tool_id);
    const content = event.preview || event.result || "done";
    if (message) {
      message.content = content;
      renderMessages();
    } else {
      appendMessage({ id: event.tool_id, role: "tool", title: event.name, subtitle: "", content });
    }
    return;
  }
  if (event.type === "background_task") {
    appendMessage({
      id: crypto.randomUUID(),
      role: "status",
      title: event.command,
      content: event.detail ? `${event.status}: ${event.detail}` : event.status,
    });
  }
}

async function sendMessage(text: string) {
  if (!state.currentSessionId || !text.trim()) return;
  if (state.editingId) {
    const idx = state.messages.findIndex(item => item.id === state.editingId);
    if (idx >= 0) state.messages = state.messages.slice(0, idx);
    state.editingId = null;
  }
  appendMessage({ id: crypto.randomUUID(), role: "user", content: text.trim() });
  state.running = true;
  renderRunChip();
  try {
    await api<{ run_id: string }>("/chat/message", {
      method: "POST",
      body: JSON.stringify({
        message: text.trim(),
        session_id: state.currentSessionId,
      }),
    });
  } catch (error) {
    state.running = false;
    appendMessage({
      id: crypto.randomUUID(),
      role: "error",
      content: error instanceof Error ? error.message : String(error),
    });
  }
}

async function switchSession(sessionId: string) {
  state.currentSessionId = sessionId;
  state.usage = { lastPrompt: 0, totalTokens: 0, totalCost: 0 };
  state.editingId = null;
  await loadHistory(sessionId);
  connectEvents(sessionId);
  render();
}

async function createSession() {
  const session = await api<SessionListItem>("/sessions", { method: "POST", body: "{}" });
  state.sessions = [session, ...state.sessions];
  await switchSession(session.session_id);
}

function formatAge(value: string) {
  const delta = Date.now() - new Date(value).getTime();
  const minutes = Math.max(1, Math.floor(delta / 60_000));
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

function escapeHtml(value: string) {
  return value.replace(/[&<>"']/g, char => {
    const entities: Record<string, string> = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "\"": "&quot;",
      "'": "&#39;",
    };
    return entities[char];
  });
}

function hostFromUrl(value: string) {
  try {
    return new URL(value).host || value;
  } catch {
    return value;
  }
}

const ICONS = {
  pencil: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor"><path d="M11.5 2.5l2 2-7 7-2.5.5.5-2.5 7-7z" stroke-linejoin="round" stroke-linecap="round"/></svg>',
  gear: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor"><circle cx="8" cy="8" r="2.2"/><path d="M8 1.5v1.8M8 12.7v1.8M3.4 3.4l1.3 1.3M11.3 11.3l1.3 1.3M1.5 8h1.8M12.7 8h1.8M3.4 12.6l1.3-1.3M11.3 4.7l1.3-1.3" stroke-linecap="round"/></svg>',
  search: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor"><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5L14 14" stroke-linecap="round"/></svg>',
  terminal: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor"><path d="M3 5l2.5 2.5L3 10M7 11h6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  brain: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor"><path d="M5.5 3a2 2 0 0 0-2 2 1.8 1.8 0 0 0-1 3.2A2 2 0 0 0 4 11.8 2 2 0 0 0 8 12V4a2 2 0 0 0-2.5-1z M10.5 3a2 2 0 0 1 2 2 1.8 1.8 0 0 1 1 3.2 2 2 0 0 1-1.5 3.6A2 2 0 0 1 8 12" stroke-linejoin="round" stroke-linecap="round"/></svg>',
  plus: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor"><path d="M8 3v10M3 8h10" stroke-linecap="round"/></svg>',
  arrowUp: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor"><path d="M8 13V3M4 7l4-4 4 4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  shield: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor"><path d="M8 1.5l5.5 2v4.2c0 3-2.3 5.5-5.5 6.8-3.2-1.3-5.5-3.8-5.5-6.8V3.5L8 1.5z" stroke-linejoin="round"/></svg>',
  close: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor"><path d="M3.5 3.5l9 9M12.5 3.5l-9 9" stroke-linecap="round"/></svg>',
  play: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor"><path d="M5 3.5l7 4.5-7 4.5V3.5z" stroke-linejoin="round" fill="currentColor"/></svg>',
  more: '<svg viewBox="0 0 16 16" fill="currentColor" stroke="none"><circle cx="3.5" cy="8" r="1.2"/><circle cx="8" cy="8" r="1.2"/><circle cx="12.5" cy="8" r="1.2"/></svg>',
  copy: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="8" y="8" rx="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>',
  edit: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>',
};

function resizeComposer(input: HTMLTextAreaElement) {
  input.style.height = "0px";
  input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
}

function readConnectionFormConfig(): AppConfig {
  const serverUrl = document.querySelector<HTMLInputElement>("#settings-server-url")?.value;
  const apiKey = document.querySelector<HTMLInputElement>("#settings-api-key")?.value;
  return normalizeConfig({
    serverUrl: serverUrl ?? state.connectionDraft.serverUrl,
    apiKey: apiKey ?? state.connectionDraft.apiKey,
  });
}

function openSettings() {
  state.connectionDraft = { ...state.config };
  state.connectionError = null;
  state.settingsOpen = true;
  mountSettingsModal();
}

function closeSettings() {
  if (state.connectionSaving) return;
  state.settingsOpen = false;
  state.connectionError = null;
  unmountSettingsModal();
}

function mountSettingsModal() {
  unmountSettingsModal();
  const wrapper = document.createElement("div");
  wrapper.id = "modal-root";
  wrapper.innerHTML = renderSettingsDialog();
  appRoot.appendChild(wrapper);
  bindSettingsEvents();
  document.querySelector<HTMLInputElement>("#settings-server-url")?.focus();
}

function unmountSettingsModal() {
  document.querySelector("#modal-root")?.remove();
}

function refreshSettingsModal() {
  const wrapper = document.querySelector("#modal-root");
  if (!wrapper) return;
  const focused = document.activeElement;
  const focusedId = focused instanceof HTMLInputElement ? focused.id : null;
  const start = focused instanceof HTMLInputElement ? focused.selectionStart : null;
  const end = focused instanceof HTMLInputElement ? focused.selectionEnd : null;
  wrapper.innerHTML = renderSettingsDialog();
  bindSettingsEvents();
  if (focusedId) {
    const el = document.querySelector<HTMLInputElement>(`#${focusedId}`);
    el?.focus();
    if (start !== null && end !== null) el?.setSelectionRange(start, end);
  }
}

function bindSettingsEvents() {
  document.querySelector<HTMLButtonElement>("#close-settings")?.addEventListener("click", closeSettings);
  document.querySelector<HTMLButtonElement>("#cancel-settings")?.addEventListener("click", closeSettings);

  document.querySelector<HTMLInputElement>("#settings-server-url")?.addEventListener("input", event => {
    state.connectionDraft.serverUrl = (event.target as HTMLInputElement).value;
  });
  document.querySelector<HTMLInputElement>("#settings-api-key")?.addEventListener("input", event => {
    state.connectionDraft.apiKey = (event.target as HTMLInputElement).value;
  });

  document.querySelector<HTMLFormElement>("#connection-form")?.addEventListener("submit", event => {
    event.preventDefault();
    void (async () => {
      state.connectionSaving = true;
      state.connectionError = null;
      state.connectionDraft = readConnectionFormConfig();
      refreshSettingsModal();
      try {
        const nextConfig = state.connectionDraft;
        await validateConnection(nextConfig);
        await saveConfig(nextConfig);
        state.settingsOpen = false;
        state.connectionError = null;
        unmountSettingsModal();
        await refresh();
      } catch (error) {
        state.connectionError = error instanceof Error ? error.message : String(error);
        refreshSettingsModal();
      } finally {
        state.connectionSaving = false;
        if (state.settingsOpen) refreshSettingsModal();
      }
    })();
  });

  document.querySelector<HTMLFormElement>("#connection-form")?.addEventListener("keydown", event => {
    if (event.key !== "Escape") return;
    closeSettings();
  });
}

function render() {
  const focused = document.activeElement;
  const focusedId =
    focused instanceof HTMLInputElement || focused instanceof HTMLTextAreaElement ? focused.id : null;
  const selectionStart =
    focused instanceof HTMLInputElement || focused instanceof HTMLTextAreaElement ? focused.selectionStart : null;
  const selectionEnd =
    focused instanceof HTMLInputElement || focused instanceof HTMLTextAreaElement ? focused.selectionEnd : null;
  const currentSession = state.sessions.find(session => session.session_id === state.currentSessionId);
  const connected = state.connected;
  const sessionLabel = currentSession?.name || (state.currentSessionId ? "untitled" : "no session");
  const sessionMeta = state.currentSessionId ? `${state.currentSessionId.slice(0, 8)}` : "—";
  const hasDraft = state.draft.trim().length > 0;

  const priorMessages = document.querySelector<HTMLElement>(".messages");
  const priorScrollTop = priorMessages?.scrollTop ?? null;
  const priorStuckBottom = priorMessages ? isAtBottom(priorMessages) : true;

  appRoot.innerHTML = `
    <aside class="sidebar">
      <div class="drag-spacer"></div>
      <div class="brand">
        <div class="brand-mark">n</div>
        <span class="brand-name">ntrp</span>
        <span class="brand-meta">v${escapeHtml(window.ntrpDesktop?.version?.() ?? "dev")}</span>
      </div>

      <nav class="nav">
        <button class="nav-item" id="new-session" type="button">
          <span class="nav-icon">${ICONS.pencil}</span>
          <span>New session</span>
        </button>
        <button class="nav-item" id="open-settings" type="button">
          <span class="nav-icon">${ICONS.gear}</span>
          <span>Settings</span>
        </button>
      </nav>

      <div class="section-label">
        <span>Sessions</span>
        ${state.sessions.length ? `<span>${state.sessions.length}</span>` : ""}
      </div>

      <div class="session-list">
        ${state.sessions.length === 0
          ? `<div class="empty-sessions">${connected ? "No sessions yet." : "Connect to load sessions."}</div>`
          : state.sessions.map(session => `
            <button class="session ${session.session_id === state.currentSessionId ? "active" : ""}" data-session="${session.session_id}" type="button">
              <span class="session-title">${escapeHtml(session.name || "untitled")}</span>
              <span class="session-age">${formatAge(session.last_activity)}</span>
            </button>
          `).join("")}
      </div>

      <div class="sidebar-footer">
        <button class="connection-pill" id="footer-settings" type="button" title="${escapeHtml(state.error || (connected ? "Connected" : "Click to configure"))}">
          <span class="dot ${connected ? "ok" : state.error ? "bad" : "warn"}"></span>
          <span class="connection-text">
            <span class="connection-status">${connected ? "Connected" : state.error ? "Connection error" : "Not connected"}</span>
            <span class="connection-host">${escapeHtml(hostFromUrl(state.config.serverUrl))}</span>
          </span>
          <span class="gear-button" aria-hidden="true">${ICONS.gear}</span>
        </button>
      </div>
    </aside>

    <main class="chat">
      <div class="chat-header">
        <div class="chat-title-wrap">
          <h1 class="chat-title">${escapeHtml(sessionLabel)}</h1>
          <span class="chat-subtitle">${escapeHtml(sessionMeta)}</span>
        </div>
        <span class="run-chip ${state.running ? "running" : "idle"}">
          <span class="pulse-dot"></span>
          ${state.running ? "running" : "idle"}
        </span>
        <button class="icon-button" type="button" aria-label="More" tabindex="-1">${ICONS.more}</button>
      </div>

      <section class="messages">
        <div class="messages-inner">
          ${state.messages.length === 0 ? renderEmptyState(connected) : state.messages.map(renderMessage).join("")}
        </div>
      </section>

      <div class="composer-wrap">
        <form class="composer" id="composer">
          <textarea id="message-input" rows="1" placeholder="Message ntrp…">${escapeHtml(state.draft)}</textarea>
          <div class="composer-bar">
            <span class="composer-usage">${usageText()}</span>
            <span class="composer-spacer"></span>
            <button class="send-button" id="composer-send" type="submit" ${state.running || !connected || !hasDraft ? "disabled" : ""} aria-label="Send">
              ${ICONS.arrowUp}
            </button>
          </div>
        </form>
      </div>
    </main>

  `;

  const newMessages = document.querySelector<HTMLElement>(".messages");
  if (newMessages) {
    if (priorStuckBottom || priorScrollTop === null) {
      newMessages.scrollTop = newMessages.scrollHeight;
    } else {
      newMessages.scrollTop = priorScrollTop;
    }
  }

  if (state.settingsOpen) mountSettingsModal();

  document.querySelector<HTMLButtonElement>("#open-settings")?.addEventListener("click", openSettings);
  document.querySelector<HTMLButtonElement>("#footer-settings")?.addEventListener("click", openSettings);

  document.querySelector<HTMLButtonElement>("#new-session")?.addEventListener("click", () => void createSession());

  document.querySelectorAll<HTMLButtonElement>("[data-session]").forEach(button => {
    button.addEventListener("click", () => {
      const sessionId = button.dataset.session;
      if (sessionId) void switchSession(sessionId);
    });
  });

  document.querySelector<HTMLElement>(".messages")?.addEventListener("click", event => {
    const target = (event.target as HTMLElement).closest<HTMLElement>("[data-action]");
    if (!target) return;
    const action = target.dataset.action;
    const messageId = target.dataset.id;
    if (!messageId) return;
    if (action === "copy") void copyMessage(messageId, target);
    else if (action === "edit") editMessage(messageId);
  });

  document.querySelector<HTMLFormElement>("#composer")?.addEventListener("submit", event => {
    event.preventDefault();
    const input = document.querySelector<HTMLTextAreaElement>("#message-input");
    if (!input) return;
    const text = input.value;
    state.draft = "";
    input.value = "";
    resizeComposer(input);
    void sendMessage(text);
  });

  const input = document.querySelector<HTMLTextAreaElement>("#message-input");
  input?.addEventListener("keydown", event => {
    if (event.key !== "Enter" || event.shiftKey) return;
    event.preventDefault();
    input.form?.requestSubmit();
  });
  input?.addEventListener("input", () => {
    const previousHasDraft = (state.draft.trim().length > 0);
    state.draft = input.value;
    resizeComposer(input);
    const hasDraft = state.draft.trim().length > 0;
    if (hasDraft !== previousHasDraft) {
      const send = document.querySelector<HTMLButtonElement>("#composer-send");
      if (send) send.disabled = state.running || !state.connected || !hasDraft;
    }
  });
  if (input) resizeComposer(input);

  let restoredFocus = false;
  if (focusedId) {
    const nextFocused = document.querySelector<HTMLInputElement | HTMLTextAreaElement>(`#${focusedId}`);
    if (nextFocused) {
      nextFocused.focus();
      restoredFocus = true;
      if (selectionStart !== null && selectionEnd !== null) {
        nextFocused.setSelectionRange(selectionStart, selectionEnd);
      }
    }
  }
  if (state.settingsOpen && !restoredFocus) {
    document.querySelector<HTMLInputElement>("#settings-server-url")?.focus();
  }
}

function renderSettingsDialog() {
  return `
    <div class="modal-backdrop">
      <form class="modal" id="connection-form">
        <div class="modal-head">
          <div>
            <span class="modal-kicker">Connection</span>
            <div class="modal-title">Connect to ntrp</div>
            <div class="modal-subtitle">Server URL and API key. Stored locally; encrypted with safeStorage when available.</div>
          </div>
          <button id="close-settings" class="modal-close" type="button" ${state.connectionSaving ? "disabled" : ""} aria-label="Close">${ICONS.close}</button>
        </div>

        <div class="field">
          <label for="settings-server-url">Server URL</label>
          <input id="settings-server-url" value="${escapeHtml(state.connectionDraft.serverUrl)}" spellcheck="false" placeholder="http://localhost:6877" />
          <span class="field-help">The address where your ntrp server is running.</span>
        </div>

        <div class="field">
          <label for="settings-api-key">API key</label>
          <input id="settings-api-key" value="${escapeHtml(state.connectionDraft.apiKey)}" spellcheck="false" type="password" autocomplete="off" placeholder="ntrp_…" />
          <span class="field-help">From your server config. Used as a Bearer token.</span>
        </div>

        ${state.connectionError ? `
          <div class="modal-error">
            <strong>Could not connect</strong>
            <span>${escapeHtml(state.connectionError)}</span>
          </div>
        ` : ""}

        <div class="modal-actions">
          <button id="cancel-settings" class="btn btn-secondary" type="button" ${state.connectionSaving ? "disabled" : ""}>Cancel</button>
          <button class="btn btn-primary" type="submit" ${state.connectionSaving ? "disabled" : ""}>
            ${state.connectionSaving ? "Checking…" : "Save & reconnect"}
          </button>
        </div>
      </form>
    </div>
  `;
}

function renderEmptyState(connected: boolean) {
  return `
    <div class="empty-state">
      <h2>${connected ? "What's on your mind?" : "Connect to get started"}</h2>
      <p>${connected ? "Send a message to begin a new exchange." : "Open settings to point ntrp at your server."}</p>
    </div>
  `;
}

function renderMessageBodyHtml(message: UiMessage): string {
  if (message.role === "assistant" || message.role === "reasoning") {
    return renderMarkdown(message.content || "");
  }
  if (message.role === "status") {
    return `${message.title ? `${escapeHtml(message.title)} · ` : ""}${escapeHtml(message.content || " ")}`;
  }
  return escapeHtml(message.content || " ");
}

function renderMessageActions(message: UiMessage): string {
  if (message.role !== "user" && message.role !== "assistant" && message.role !== "reasoning") return "";
  const id = escapeHtml(message.id);
  const editBtn = message.role === "user"
    ? `<button class="message-action" data-action="edit" data-id="${id}" type="button" title="Edit and resend">${ICONS.edit}</button>`
    : "";
  return `
    <div class="message-actions">
      <button class="message-action" data-action="copy" data-id="${id}" type="button" title="Copy">${ICONS.copy}</button>
      ${editBtn}
    </div>
  `;
}

function renderMessage(message: UiMessage) {
  const id = escapeHtml(message.id);
  if (message.role === "user") {
    return `
      <article class="message user" data-id="${id}">
        <div class="message-body">${renderMessageBodyHtml(message)}</div>
        ${renderMessageActions(message)}
      </article>
    `;
  }
  if (message.role === "assistant") {
    return `
      <article class="message assistant" data-id="${id}">
        <div class="message-body">${renderMessageBodyHtml(message)}</div>
        ${renderMessageActions(message)}
      </article>
    `;
  }
  const isLast = state.messages[state.messages.length - 1]?.id === message.id;
  if (message.role === "reasoning") {
    const isStreaming = isLast && state.running;
    return `
      <article class="message reasoning" data-id="${id}" data-state="${isStreaming ? "streaming" : "done"}">
        <div class="message-head">${ICONS.brain}<span>${escapeHtml(message.title || "Reasoning")}</span></div>
        <div class="message-body">${renderMessageBodyHtml(message)}</div>
        ${renderMessageActions(message)}
      </article>
    `;
  }
  if (message.role === "tool") {
    const isRunning = !message.content;
    return `
      <article class="message tool" data-id="${id}" data-state="${isRunning ? "running" : "done"}">
        <div class="tool-line">
          <span class="tool-glyph">↗</span>
          <span class="tool-name">${escapeHtml(message.title || "tool")}</span>
          <span class="tool-arg">${escapeHtml(message.subtitle || "")}</span>
        </div>
        ${!isRunning ? `<div class="tool-preview">${escapeHtml(message.content)}</div>` : ""}
      </article>
    `;
  }
  if (message.role === "error") {
    return `
      <article class="message error" data-id="${id}">
        <div class="message-body">${renderMessageBodyHtml(message)}</div>
      </article>
    `;
  }
  return `
    <article class="message status" data-id="${id}">
      <div class="message-body">${renderMessageBodyHtml(message)}</div>
    </article>
  `;
}

render();
void (async () => {
  try {
    state.config = await loadInitialConfig();
    state.connectionDraft = { ...state.config };
  } catch (error) {
    state.error = error instanceof Error ? error.message : String(error);
  }
  await refresh();
})();
