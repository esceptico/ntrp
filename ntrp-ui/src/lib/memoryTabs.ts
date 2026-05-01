export const MEMORY_TABS = [
  "overview",
  "recall",
  "context",
  "profile",
  "facts",
  "observations",
  "prune",
  "learning",
  "events",
] as const;

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
    wide: "Home",
    narrow: "Home",
    title: "Home",
    description: "health, counts, and where to go next",
  },
  recall: {
    wide: "Search",
    narrow: "Find",
    title: "Search",
    description: "test what memory retrieval returns for a query",
  },
  context: {
    wide: "Sent",
    narrow: "Sent",
    title: "Sent",
    description: "memory bundles that reached prompts or tools",
  },
  profile: {
    wide: "Profile",
    narrow: "Prof",
    title: "Profile",
    description: "always-on identity, preference, and constraint facts",
  },
  facts: {
    wide: "Facts",
    narrow: "Facts",
    title: "Facts",
    description: "direct durable memory records",
  },
  observations: {
    wide: "Patterns",
    narrow: "Pat",
    title: "Patterns",
    description: "derived summaries backed by facts",
  },
  prune: {
    wide: "Cleanup",
    narrow: "Clean",
    title: "Cleanup",
    description: "bulk archive low-value derived patterns",
  },
  learning: {
    wide: "Improve",
    narrow: "Learn",
    title: "Improve",
    description: "review durable policy, prompt, and skill proposals",
  },
  events: {
    wide: "Audit",
    narrow: "Audit",
    title: "Audit",
    description: "why memory changed and who changed it",
  },
};

export function memoryTabLabels(width: number): Record<MemoryTabType, string> {
  const key = width < 95 ? "narrow" : "wide";
  return Object.fromEntries(
    MEMORY_TABS.map((tab) => [tab, MEMORY_TAB_COPY[tab][key]])
  ) as Record<MemoryTabType, string>;
}
