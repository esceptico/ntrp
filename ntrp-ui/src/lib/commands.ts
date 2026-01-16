import type { SlashCommand } from "../types.js";

export const COMMANDS: SlashCommand[] = [
  { name: "init", description: "Scan vault and learn about you" },
  { name: "index", description: "Re-index notes for semantic search" },
  { name: "memory", description: "View memory (facts, observations)" },
  { name: "config", description: "View configuration" },
  { name: "connections", description: "Manage data sources (vault, gmail, browser)" },
  { name: "settings", description: "Model, UI, and agent settings" },
  { name: "context", description: "Show token usage breakdown" },
  { name: "compact", description: "Summarize old messages to save tokens" },
  { name: "clear", description: "Clear chat history" },
  { name: "purge", description: "Clear graph memory (keeps note embeddings)" },
  { name: "exit", description: "Exit application" },
];
