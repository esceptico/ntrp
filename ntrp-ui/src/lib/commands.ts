import type { SlashCommand } from "../types.js";

export const COMMANDS = [
  { name: "new", description: "Start a new session" },
  { name: "sessions", description: "Switch, create, or delete sessions" },
  { name: "name", description: "Rename current session" },
  { name: "delete", description: "Delete a session" },
  { name: "init", description: "Scan vault and learn about you" },
  { name: "index", description: "Re-index notes for semantic search" },
  { name: "memory", description: "View memory (facts, observations)" },
  { name: "automations", description: "View and manage automations" },
  { name: "theme", description: "Choose a theme" },
  { name: "connect", description: "Manage LLM providers" },
  { name: "models", description: "Switch models (agent, explore, memory, embedding)" },
  { name: "settings", description: "Model, connections, and UI settings" },
  { name: "compact", description: "Summarize old messages to save tokens" },
  { name: "clear", description: "Clear current session messages" },
  { name: "purge", description: "Clear graph memory (keeps note embeddings)" },
  { name: "logout", description: "Clear credentials and disconnect" },
  { name: "exit", description: "Exit application" },
] as const satisfies readonly SlashCommand[];
