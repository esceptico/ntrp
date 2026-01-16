export type TabId = "ui" | "agent";

export const TAB_IDS: TabId[] = ["ui", "agent"];
export const TAB_LABELS: Record<TabId, string> = { ui: "UI", agent: "Agent" };

export interface BooleanItem {
  key: string;
  description: string;
}

export const BOOLEAN_ITEMS: BooleanItem[] = [
  { key: "renderMarkdown", description: "Format messages with markdown styling" },
];

export interface NumberItem {
  key: string;
  description: string;
  min: number;
  max: number;
}

export const NUMBER_ITEMS: NumberItem[] = [
  { key: "maxDepth", description: "Subagent nesting level", min: 1, max: 16 },
  { key: "maxIterations", description: "Tool call iterations per query", min: 1, max: 25 },
];

export const COL_CURSOR = 2;
export const COL_CHECK = 5;
export const COL_NUMBER = 8;

export function pad(s: string, w: number): string {
  return s.padEnd(w);
}
