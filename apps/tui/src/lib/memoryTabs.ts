export const MEMORY_TABS = ["today", "graph", "skills", "search"] as const;

export type MemoryTabType = (typeof MEMORY_TABS)[number];

export const MEMORY_TAB_COPY: Record<
  MemoryTabType,
  {
    wide: string;
    narrow: string;
    title: string;
    description: string;
  }
> = {
  today: {
    wide: "Today",
    narrow: "Today",
    title: "Today",
    description: "review proposals, corrections, and fresh memory",
  },
  graph: {
    wide: "Graph",
    narrow: "Graph",
    title: "Graph",
    description: "provenance DAG for memory items",
  },
  skills: {
    wide: "Skills",
    narrow: "Skills",
    title: "Skills",
    description: "toolable procedures and proposals",
  },
  search: {
    wide: "Search",
    narrow: "Search",
    title: "Search",
    description: "hybrid memory search with filters",
  },
};

export function memoryTabLabels(width: number): Record<MemoryTabType, string> {
  if (width < 82) {
    return Object.fromEntries(
      MEMORY_TABS.map((tab, index) => [tab, String(index + 1)])
    ) as Record<MemoryTabType, string>;
  }
  const key = width < 110 ? "narrow" : "wide";
  return Object.fromEntries(
    MEMORY_TABS.map((tab) => [tab, MEMORY_TAB_COPY[tab][key]])
  ) as Record<MemoryTabType, string>;
}
