import React from "react";
import { Hints } from "../../ui/index.js";
import type { RecallInspectTabState } from "../../../hooks/useRecallInspectTab.js";
import type { MemoryTabType } from "../../../lib/memoryTabs.js";

interface MemoryFooterProps {
  activeTab: MemoryTabType;
  recallTab: RecallInspectTabState;
  factsTab: { editMode: boolean; confirmDelete: boolean; focusPane: string; searchMode: boolean };
  obsTab: { editMode: boolean; confirmDelete: boolean; focusPane: string; searchMode: boolean };
  pruneTab: { focusPane: string; searchMode: boolean; confirmApply: "selected" | "all" | null };
  accessTab: { focusPane: string; searchMode: boolean };
  eventsTab: { focusPane: string; searchMode: boolean };
}

export function MemoryFooter({ activeTab, recallTab, factsTab, obsTab, pruneTab, accessTab, eventsTab }: MemoryFooterProps): React.ReactNode {
  if (activeTab === "recall") {
    const hints: [string, string][] = recallTab.inputActive
      ? [["type", "query"], ["enter", "inspect"], ["esc", "done"], ["^u", "clear"]]
      : [["enter", "edit query"], ["↑↓", "scroll"], ["^u", "clear"], ["esc", "close"]];
    if (recallTab.loading) hints.unshift(["...", "running"]);
    return <Hints items={hints} />;
  }

  if (activeTab === "prune") {
    if (pruneTab.confirmApply) return <Hints items={[["y", "confirm"], ["any", "cancel"]]} />;
    if (pruneTab.focusPane === "details") {
      return <Hints items={[["↑↓", "navigate"], ["tab", "list"], ["a", "archive"], ["A", "archive all"], ["r", "refresh"]]} />;
    }
    if (pruneTab.searchMode) return <Hints items={[["type", "search"], ["esc", "clear/exit"], ["enter", "done"]]} />;
    return <Hints items={[["↑↓", "navigate"], ["tab", "details"], ["/", "search"], ["a", "archive"], ["A", "archive all"], ["o", "sort"], ["r", "refresh"]]} />;
  }

  if (activeTab === "context") {
    if (accessTab.focusPane === "details") {
      return <Hints items={[["↑↓", "navigate"], ["tab", "list"], ["r", "refresh"]]} />;
    }
    if (accessTab.searchMode) return <Hints items={[["type", "search"], ["esc", "clear/exit"], ["enter", "done"]]} />;
    return <Hints items={[["↑↓", "navigate"], ["tab", "details"], ["/", "search"], ["s", "source"], ["o", "sort"], ["r", "refresh"]]} />;
  }

  if (activeTab === "events") {
    if (eventsTab.focusPane === "details") {
      return <Hints items={[["↑↓", "navigate"], ["tab", "list"], ["r", "refresh"]]} />;
    }
    if (eventsTab.searchMode) return <Hints items={[["type", "search"], ["esc", "clear/exit"], ["enter", "done"]]} />;
    return <Hints items={[["↑↓", "navigate"], ["tab", "details"], ["/", "search"], ["x", "target"], ["u", "actor"], ["v", "action"], ["o", "sort"], ["r", "refresh"]]} />;
  }

  const tab = activeTab === "facts" ? factsTab : obsTab;

  if (tab.editMode) return <Hints items={[["^s", "save"], ["esc", "cancel"], ["←→", "cursor"]]} />;
  if (tab.confirmDelete) return <Hints items={[["y", "confirm"], ["any", "cancel"]]} />;
  if (tab.focusPane === "details") {
    const detailHints: [string, string][] = [["↑↓", "navigate"], ["tab", "list"], ["enter", activeTab === "observations" ? "open/expand" : "expand"], ["e", "edit"]];
    detailHints.push(["d", "del"]);
    return <Hints items={detailHints} />;
  }
  if (tab.searchMode) return <Hints items={[["type", "search"], ["esc", "clear/exit"], ["enter", "done"]]} />;
  const listHints: [string, string][] = [
    ["↑↓", "navigate"],
    ["tab", "details"],
    ["/", "search"],
    ["e", "edit"],
    ["d", "del"],
    ...(activeTab === "facts" ? [
      ["m", "kind"] as [string, string],
      ["l", "life"] as [string, string],
      ["x", "status"] as [string, string],
      ["s", "source"] as [string, string],
      ["u", "used"] as [string, string],
    ] : activeTab === "observations" ? [
      ["x", "status"] as [string, string],
      ["u", "used"] as [string, string],
      ["v", "support"] as [string, string],
    ] : []),
    ["o", "sort"],
  ];
  return <Hints items={listHints} />;
}
