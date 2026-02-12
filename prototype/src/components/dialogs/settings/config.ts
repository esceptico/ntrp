export const SECTION_IDS = ["agent", "connections", "skills", "notifiers", "appearance", "limits"] as const;
export type SectionId = (typeof SECTION_IDS)[number];

export const SECTION_LABELS = {
  agent: "Agent",
  connections: "Connections",
  skills: "Skills",
  notifiers: "Notifiers",
  appearance: "Appearance",
  limits: "Limits",
} satisfies Record<SectionId, string>;

export interface BooleanItem {
  key: string;
  label: string;
  description: string;
}

export interface NumberItem {
  key: string;
  label: string;
  description: string;
  min: number;
  max: number;
}

export const APPEARANCE_ITEMS: BooleanItem[] = [
  { key: "renderMarkdown", label: "Markdown", description: "Format messages with markdown styling" },
];

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
