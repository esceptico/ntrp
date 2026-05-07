export type MemoryTab = "search" | "facts" | "patterns" | "sent" | "cleanup" | "audit";

const ADVANCED_TABS = new Set<MemoryTab>(["sent", "cleanup", "audit"]);

export function isAdvancedMemoryTab(tab: MemoryTab): boolean {
  return ADVANCED_TABS.has(tab);
}

export function advancedMemoryTabsVisible(activeTab: MemoryTab, expanded: boolean): boolean {
  return expanded || isAdvancedMemoryTab(activeTab);
}
