import React from "react";
import { Hints } from "../../ui/index.js";
import type { RecallInspectTabState } from "../../../hooks/useRecallInspectTab.js";
import { MEMORY_TABS, type MemoryTabType } from "../../../lib/memoryTabs.js";
import {
  canApplyLearningCandidate,
  canApproveLearningCandidate,
  canRejectLearningCandidate,
  canRevertLearningCandidate,
} from "../../../lib/memoryLearning.js";

interface MemoryFooterProps {
  activeTab: MemoryTabType;
  recallTab: RecallInspectTabState;
  factsTab: { editMode: boolean; confirmDelete: boolean; focusPane: string; searchMode: boolean; metadataSuggestion: unknown };
  obsTab: { editMode: boolean; confirmDelete: boolean; focusPane: string; searchMode: boolean };
  pruneTab: { focusPane: string; searchMode: boolean; confirmApply: "selected" | "all" | null };
  learningTab: {
    focusPane: string;
    searchMode: boolean;
    confirmStatus: "approved" | "applied" | "rejected" | "reverted" | null;
    confirmProposalScan: boolean;
    selectedCandidate: { status: string } | null;
  };
  accessTab: { focusPane: string; searchMode: boolean };
  eventsTab: { focusPane: string; searchMode: boolean };
}

export function MemoryFooter({ activeTab, recallTab, factsTab, obsTab, pruneTab, learningTab, accessTab, eventsTab }: MemoryFooterProps): React.ReactNode {
  if (activeTab === "overview") {
    return <Hints items={[[`1-${MEMORY_TABS.length}`, "tabs"], ["r", "refresh"], ["q", "close"]]} />;
  }

  if (activeTab === "recall") {
    const hints: [string, string][] = [["enter", "inspect"], ["↑↓", "scroll"], ["^u", "clear"], ["esc", "close"]];
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

  if (activeTab === "learning") {
    if (learningTab.confirmProposalScan) {
      return <Hints items={[["y", "create proposals"], ["n/esc", "cancel"]]} />;
    }
    if (learningTab.confirmStatus) {
      const action =
        learningTab.confirmStatus === "approved"
          ? "approve"
          : learningTab.confirmStatus === "applied"
            ? "apply"
            : learningTab.confirmStatus === "reverted"
              ? "revert"
              : "reject";
      return <Hints items={[["y", action], ["n/esc", "cancel"]]} />;
    }
    const selectedStatus = learningTab.selectedCandidate?.status;
    const canApprove = canApproveLearningCandidate(selectedStatus);
    const canApply = canApplyLearningCandidate(selectedStatus);
    const canReject = canRejectLearningCandidate(selectedStatus);
    const canRevert = canRevertLearningCandidate(selectedStatus);
    const reviewHints: [string, string][] = [];
    if (canApprove) reviewHints.push(["a", "approve"]);
    if (canApply) reviewHints.push(["a", "apply"]);
    if (canReject) reviewHints.push(["d", "reject"]);
    if (canRevert) reviewHints.push(["z", "revert"]);
    reviewHints.push(["p", "create proposals"], ["r", "refresh"]);
    if (learningTab.searchMode) return <Hints items={[["type", "search"], ["esc", "clear/exit"], ["enter", "done"]]} />;
    return <Hints items={[["↑↓", "select"], ["/", "search"], ["l", "lane"], ["s", "status"], ["v", "type"], ...reviewHints, ["p", "scan"], ["r", "refresh"], ["o", "sort"]]} />;
  }

  const tab = activeTab === "facts" ? factsTab : obsTab;

  if (tab.editMode) return <Hints items={[["^s", "save"], ["esc", "cancel"], ["←→", "cursor"]]} />;
  if (tab.confirmDelete) return <Hints items={[["y", "confirm"], ["any", "cancel"]]} />;
  if (tab.focusPane === "details") {
    const detailHints: [string, string][] = [["↑↓", "navigate"], ["tab", "list"], ["enter", activeTab === "observations" ? "open/expand" : "expand"], ["e", "edit"]];
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
      ["l", "life"] as [string, string],
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
