import type { SlashCommand } from "../types.js";

export const COMMANDS = [
  { name: "init", description: "Scan vault and learn about you" },
  { name: "index", description: "Re-index notes for semantic search" },
  { name: "memory", description: "View memory (facts, observations)" },
  { name: "schedules", description: "View and manage scheduled tasks" },
  { name: "settings", description: "Model, connections, and UI settings" },
  { name: "dashboard", description: "Server dashboard and diagnostics" },
  { name: "compact", description: "Summarize old messages to save tokens" },
  { name: "clear", description: "Clear chat history" },
  { name: "purge", description: "Clear graph memory (keeps note embeddings)" },
  { name: "exit", description: "Exit application" },
] as const satisfies readonly SlashCommand[];
