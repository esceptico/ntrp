import React from "react";
import { Hints } from "../../ui/index.js";

type TabType = "facts" | "observations" | "dreams";

interface MemoryFooterProps {
  activeTab: TabType;
  factsTab: { editMode: boolean; confirmDelete: boolean; focusPane: string; searchMode: boolean; metadataSuggestion: unknown };
  obsTab: { editMode: boolean; confirmDelete: boolean; focusPane: string; searchMode: boolean };
  dreamsTab: { confirmDelete: boolean; focusPane: string; searchMode: boolean };
}

export function MemoryFooter({ activeTab, factsTab, obsTab, dreamsTab }: MemoryFooterProps): React.ReactNode {
  if (activeTab === "dreams") {
    if (dreamsTab.confirmDelete) return <Hints items={[["y", "confirm"], ["any", "cancel"]]} />;
    if (dreamsTab.focusPane === "details") {
      return <Hints items={[["↑↓", "navigate"], ["tab", "list"], ["enter", "expand"], ["d", "del"]]} />;
    }
    if (dreamsTab.searchMode) return <Hints items={[["type", "search"], ["esc", "clear/exit"], ["enter", "done"]]} />;
    return <Hints items={[["↑↓", "navigate"], ["tab", "details"], ["/", "search"], ["d", "del"], ["o", "sort"]]} />;
  }

  const tab = activeTab === "facts" ? factsTab : obsTab;

  if (tab.editMode) return <Hints items={[["^s", "save"], ["esc", "cancel"], ["←→", "cursor"]]} />;
  if (tab.confirmDelete) return <Hints items={[["y", "confirm"], ["any", "cancel"]]} />;
  if (tab.focusPane === "details") {
    const detailHints: [string, string][] = [["↑↓", "navigate"], ["tab", "list"], ["enter", "expand"], ["e", "edit"]];
    if (activeTab === "facts") {
      detailHints.push(["g", "suggest"]);
      if (factsTab.metadataSuggestion) detailHints.push(["a", "apply"]);
    }
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
      ["x", "status"] as [string, string],
      ["s", "source"] as [string, string],
      ["u", "used"] as [string, string],
    ] : [
      ["x", "status"] as [string, string],
      ["u", "used"] as [string, string],
      ["v", "support"] as [string, string],
    ]),
    ["o", "sort"],
  ];
  return <Hints items={listHints} />;
}
