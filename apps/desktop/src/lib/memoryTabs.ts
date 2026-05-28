export type MemoryTab = "overview" | "library" | "pipeline" | "review" | "activation";

export interface MemoryTabConfig {
  id: MemoryTab;
  label: string;
}

export const MEMORY_TABS: MemoryTabConfig[] = [
  { id: "overview", label: "Overview" },
  { id: "library", label: "Library" },
  { id: "pipeline", label: "Pipeline" },
  { id: "review", label: "Review" },
  { id: "activation", label: "Activation" },
];

export function memoryTabLabels(): MemoryTabConfig[] {
  return MEMORY_TABS;
}
