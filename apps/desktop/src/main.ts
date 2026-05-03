import "./styles.css";

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

interface UiMessage {
  id: string;
  role: Role;
  title?: string;
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

const state: {
  config: AppConfig;
  sessions: SessionListItem[];
  currentSessionId: string | null;
  messages: UiMessage[];
  connected: boolean;
  running: boolean;
  error: string | null;
  eventDisconnect?: () => void;
} = {
  config: loadConfig(),
  sessions: [],
  currentSessionId: null,
  messages: [],
  connected: false,
  running: false,
  error: null,
};

function getAppRoot(): HTMLDivElement {
  const element = document.querySelector<HTMLDivElement>("#app");
  if (!element) throw new Error("Missing #app");
  return element;
}

const appRoot = getAppRoot();

function loadConfig(): AppConfig {
  const fallback = { serverUrl: "http://localhost:6877", apiKey: "" };
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return fallback;
  try {
    return { ...fallback, ...JSON.parse(raw) };
  } catch {
    return fallback;
  }
}

function saveConfig(config: AppConfig) {
  state.config = config;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
}

function headers(json = false): HeadersInit {
  const output: Record<string, string> = {};
  if (json) output["Content-Type"] = "application/json";
  if (state.config.apiKey) output.Authorization = `Bearer ${state.config.apiKey}`;
  return output;
}

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${state.config.serverUrl}${path}`, {
    ...init,
    headers: {
      ...headers(Boolean(init.body)),
      ...(init.headers ?? {}),
    },
  });

  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      message = body.detail ?? body.message ?? message;
    } catch {
      const text = await response.text();
      if (text) message = text;
    }
    throw new Error(message);
  }

  if (!response.headers.get("content-type")?.includes("application/json")) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

async function refresh() {
  try {
    await api("/health");
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

function appendMessage(message: UiMessage) {
  state.messages = [...state.messages, message];
  render();
  requestAnimationFrame(() => {
    document.querySelector(".messages")?.scrollTo({ top: 1_000_000 });
  });
}

function appendToLast(role: Role, delta: string, title?: string) {
  const last = state.messages.at(-1);
  if (last?.role === role && last.title === title) {
    last.content += delta;
    render();
    return;
  }
  appendMessage({ id: crypto.randomUUID(), role, title, content: delta });
}

function handleEvent(event: ServerEvent) {
  if (event.type === "run_started") {
    state.running = true;
    state.error = null;
    render();
    return;
  }
  if (event.type === "run_finished") {
    state.running = false;
    const usage = event.usage;
    if (usage) {
      appendMessage({
        id: crypto.randomUUID(),
        role: "status",
        content: `${usage.prompt} prompt / ${usage.completion} completion / ${usage.cache_read} cached / $${usage.cost.toFixed(4)}`,
      });
    } else {
      render();
    }
    return;
  }
  if (event.type === "run_error") {
    state.running = false;
    appendMessage({ id: crypto.randomUUID(), role: "error", content: event.message });
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
      render();
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
      content: event.description || "running",
    });
    return;
  }
  if (event.type === "tool_result") {
    const message = state.messages.find(item => item.id === event.tool_id);
    const content = event.preview || event.result || "done";
    if (message) {
      message.content = content;
      render();
    } else {
      appendMessage({ id: event.tool_id, role: "tool", title: event.name, content });
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
  appendMessage({ id: crypto.randomUUID(), role: "user", content: text.trim() });
  state.running = true;
  render();
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

function render() {
  const currentSession = state.sessions.find(session => session.session_id === state.currentSessionId);
  appRoot.innerHTML = `
    <aside class="sidebar">
      <div class="brand">
        <div>
          <strong>ntrp</strong>
          <span>desktop</span>
        </div>
        <span class="status ${state.connected ? "ok" : "bad"}">${state.connected ? "online" : "offline"}</span>
      </div>

      <section class="connection">
        <label>server</label>
        <input id="server-url" value="${escapeHtml(state.config.serverUrl)}" spellcheck="false" />
        <label>api key</label>
        <input id="api-key" value="${escapeHtml(state.config.apiKey)}" spellcheck="false" type="password" />
        <button id="save-config">connect</button>
        ${state.error ? `<p class="error">${escapeHtml(state.error)}</p>` : ""}
      </section>

      <section class="session-list">
        <div class="section-title">
          <span>sessions</span>
          <button id="new-session">new</button>
        </div>
        ${state.sessions.map(session => `
          <button class="session ${session.session_id === state.currentSessionId ? "active" : ""}" data-session="${session.session_id}">
            <span>${escapeHtml(session.name || "untitled")}</span>
            <small>${session.message_count} msgs . ${formatAge(session.last_activity)}</small>
          </button>
        `).join("")}
      </section>
    </aside>

    <main class="chat">
      <header>
        <div>
          <h1>${escapeHtml(currentSession?.name || "general")}</h1>
          <p>${escapeHtml(state.currentSessionId || "no session")}</p>
        </div>
        <div class="run-state">
          ${state.running ? `<span class="pulse"></span> running` : "idle"}
        </div>
      </header>

      <section class="messages">
        ${state.messages.map(renderMessage).join("")}
      </section>

      <form class="composer" id="composer">
        <textarea id="message-input" rows="1" placeholder="Message ntrp..."></textarea>
        <button type="submit" ${state.running || !state.connected ? "disabled" : ""}>send</button>
      </form>
    </main>
  `;

  document.querySelector<HTMLButtonElement>("#save-config")?.addEventListener("click", () => {
    const serverUrl = document.querySelector<HTMLInputElement>("#server-url")?.value.trim() || state.config.serverUrl;
    const apiKey = document.querySelector<HTMLInputElement>("#api-key")?.value.trim() || "";
    saveConfig({ serverUrl: serverUrl.replace(/\/$/, ""), apiKey });
    void refresh();
  });

  document.querySelector<HTMLButtonElement>("#new-session")?.addEventListener("click", () => void createSession());

  document.querySelectorAll<HTMLButtonElement>("[data-session]").forEach(button => {
    button.addEventListener("click", () => {
      const sessionId = button.dataset.session;
      if (sessionId) void switchSession(sessionId);
    });
  });

  document.querySelector<HTMLFormElement>("#composer")?.addEventListener("submit", event => {
    event.preventDefault();
    const input = document.querySelector<HTMLTextAreaElement>("#message-input");
    if (!input) return;
    const text = input.value;
    input.value = "";
    void sendMessage(text);
  });
}

function renderMessage(message: UiMessage) {
  return `
    <article class="message ${message.role}">
      <div class="message-role">${escapeHtml(message.title || message.role)}</div>
      <div class="message-body">${escapeHtml(message.content || " ")}</div>
    </article>
  `;
}

render();
void refresh();
