export const SECTION_IDS = ["connection", "apiKeys", "sources", "memory", "instructions", "context", "agent", "notifications", "skills", "mcp", "interface"] as const;
export type SectionId = (typeof SECTION_IDS)[number];

export const SECTION_LABELS = {
  connection: "Connection",
  apiKeys: "API Keys",
  sources: "Sources",
  memory: "Memory",
  instructions: "Instructions",
  context: "Context",
  agent: "Agent",
  notifications: "Notifications",
  skills: "Skills",
  mcp: "MCP Servers",
  interface: "Interface",
} satisfies Record<SectionId, string>;

export interface NumberItem {
  key: string;
  label: string;
  description: string;
  min: number;
  max: number;
  step?: number;
}

export const CONTEXT_ITEMS: NumberItem[] = [
  { key: "compressionThreshold", label: "Compact trigger", description: "% of context window that triggers compression", min: 50, max: 100 },
  { key: "maxMessages", label: "Max messages", description: "Message ceiling that triggers compaction", min: 20, max: 500, step: 10 },
  { key: "compressionKeepRatio", label: "Keep ratio", description: "% of recent messages preserved after compaction", min: 10, max: 80 },
  { key: "summaryMaxTokens", label: "Summary tokens", description: "Max tokens for the generated summary", min: 500, max: 4000, step: 100 },
];

export const AGENT_ITEMS: NumberItem[] = [
  { key: "maxDepth", label: "Subagent depth", description: "Maximum nesting level for sub-agent spawning", min: 1, max: 16 },
];

export const MEMORY_NUMBER_ITEMS: NumberItem[] = [
  { key: "consolidationInterval", label: "Interval", description: "Minutes between consolidation runs", min: 5, max: 120, step: 5 },
];

export const SOURCE_ITEMS = ["vault", "google", "browser", "web"] as const;
export type SourceItem = (typeof SOURCE_ITEMS)[number];

export const SOURCE_LABELS = {
  vault: "Notes",
  google: "Google",
  browser: "Browser",
  web: "Web Search",
} satisfies Record<SourceItem, string>;

export const TOGGLEABLE_SOURCES: SourceItem[] = ["google"];

export const NOTIFIER_TYPE_ORDER = ["email", "telegram", "bash"] as const;
export const NOTIFIER_TYPE_LABELS: Record<string, string> = {
  email: "Email",
  telegram: "Telegram",
  bash: "Bash",
};
export const NOTIFIER_TYPE_DESCRIPTIONS: Record<string, string> = {
  email: "Send via connected Gmail",
  telegram: "Send via Telegram bot",
  bash: "Run shell command",
};
