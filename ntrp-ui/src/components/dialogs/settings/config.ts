export const SECTION_IDS = ["server", "providers", "services", "directives", "connections", "skills", "notifiers", "mcp", "limits"] as const;
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
} satisfies Record<SectionId, string>;

export interface NumberItem {
  key: string;
  label: string;
  description: string;
  min: number;
  max: number;
}

export const LIMIT_ITEMS: NumberItem[] = [
  { key: "maxDepth", label: "Subagent depth", description: "Maximum nesting level", min: 1, max: 16 },
];

export const CONNECTION_ITEMS = ["vault", "gmail", "calendar", "browser", "memory", "web"] as const;
export type ConnectionItem = (typeof CONNECTION_ITEMS)[number];

export const CONNECTION_LABELS = {
  vault: "Notes",
  gmail: "Gmail",
  calendar: "Calendar",
  browser: "Browser",
  memory: "Memory",
  web: "Web Search",
} satisfies Record<ConnectionItem, string>;

export const TOGGLEABLE_SOURCES: ConnectionItem[] = ["gmail", "calendar", "memory"];

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
