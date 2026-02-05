export type SectionId = "agent" | "appearance" | "limits";

export const SECTION_IDS: SectionId[] = ["agent", "appearance", "limits"];
export const SECTION_LABELS: Record<SectionId, string> = {
  agent: "Agent",
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
  { key: "maxIterations", label: "Iterations", description: "Tool calls per query", min: 1, max: 25 },
];

export const COL_CURSOR = 2;
export const COL_CHECK = 5;
export const COL_NUMBER = 8;

export function pad(s: string, w: number): string {
  return s.padEnd(w);
}
