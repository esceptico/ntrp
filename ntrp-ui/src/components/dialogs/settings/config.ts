export const SECTION_IDS = ["server", "providers", "services", "directives", "connections", "skills", "notifiers", "mcp", "limits", "sidebar"] as const;
export type SectionId = (typeof SECTION_IDS)[number];

export const SECTION_LABELS = {
  server: "Server",
  providers: "Providers",
  services: "Services",
  directives: "Directives",
  connections: "Connections",
  skills: "Skills",
  notifiers: "Notifiers",
  mcp: "MCP Servers",
  limits: "Limits",
  sidebar: "Sidebar",
} satisfies Record<SectionId, string>;

export interface NumberItem {
  key: string;
  label: string;
  description: string;
  min: number;
  max: number;
  step?: number;
}

export const LIMIT_ITEMS: NumberItem[] = [
  { key: "maxDepth", label: "Subagent depth", description: "Maximum nesting level", min: 1, max: 16 },
  { key: "compressionThreshold", label: "Compact trigger", description: "% of context to trigger", min: 50, max: 100 },
  { key: "maxMessages", label: "Max messages", description: "Message ceiling for compaction", min: 20, max: 500, step: 10 },
  { key: "compressionKeepRatio", label: "Keep ratio", description: "% of recent messages to keep", min: 10, max: 80 },
  { key: "summaryMaxTokens", label: "Summary tokens", description: "Max tokens for summary", min: 500, max: 4000, step: 100 },
  { key: "consolidationInterval", label: "Consolidation", description: "Minutes between runs", min: 5, max: 120, step: 5 },
];

export const CONNECTION_ITEMS = ["vault", "google", "browser", "memory", "dreams", "web"] as const;
export type ConnectionItem = (typeof CONNECTION_ITEMS)[number];

export const CONNECTION_LABELS = {
  vault: "Notes",
  google: "Google",
  browser: "Browser",
  memory: "Memory",
  dreams: "  Dreams",
  web: "Web Search",
} satisfies Record<ConnectionItem, string>;

export const TOGGLEABLE_SOURCES: ConnectionItem[] = ["google", "memory", "dreams"];

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
