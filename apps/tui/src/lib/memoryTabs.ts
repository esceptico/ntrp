export const MEMORY_TABS = ["overview", "library", "review", "activation"] as const;

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
  overview: {
    wide: "Overview",
    narrow: "View",
    title: "Overview",
    description: "counts, review queue, recent knowledge",
  },
  library: {
    wide: "Library",
    narrow: "Types",
    title: "Library",
    description: "browse knowledge by object type",
  },
  review: {
    wide: "Review",
    narrow: "Review",
    title: "Review",
    description: "draft procedures, actions, and artifacts",
  },
  activation: {
    wide: "Activation",
    narrow: "Use",
    title: "Activation",
    description: "preview what enters the agent context",
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
