export type SectionId = "agent" | "connections" | "appearance" | "limits";

export const SECTION_IDS: SectionId[] = ["agent", "connections", "appearance", "limits"];
export const SECTION_LABELS: Record<SectionId, string> = {
  agent: "Agent",
  connections: "Connections",
  appearance: "Appearance",
  limits: "Limits",
};

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

// Appearance section
export const APPEARANCE_ITEMS: BooleanItem[] = [
  { key: "renderMarkdown", label: "Markdown", description: "Format messages with markdown styling" },
];

// Limits section
export const LIMIT_ITEMS: NumberItem[] = [
  { key: "maxDepth", label: "Subagent depth", description: "Maximum nesting level", min: 1, max: 16 },
];

// Connections section items
export type ConnectionItem = "vault" | "google" | "browser";
export const CONNECTION_ITEMS: ConnectionItem[] = ["vault", "google", "browser"];
export const CONNECTION_LABELS: Record<ConnectionItem, string> = {
  vault: "Vault",
  google: "Google",
  browser: "Browser",
};
