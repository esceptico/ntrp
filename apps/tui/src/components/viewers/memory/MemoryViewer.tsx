import { useEffect, useState } from "react";
import type { Config } from "../../../types.js";
import {
  getKnowledgeSummary,
  listKnowledgeObjects,
  type KnowledgeObject,
  type KnowledgeObjectType,
  type KnowledgeSummary,
} from "../../../api/client.js";
import { useRecallInspectTab } from "../../../hooks/useRecallInspectTab.js";
import { useKeypress } from "../../../hooks/useKeypress.js";
import { Dialog, Tabs, colors, truncateText } from "../../ui/index.js";
import { formatAge } from "../../../lib/utils.js";
import { MEMORY_TABS, MEMORY_TAB_COPY, memoryTabLabels, type MemoryTabType } from "../../../lib/memoryTabs.js";
import { KNOWLEDGE_LIBRARY_TYPES, knowledgeSurfaceCount, reviewKind, shouldReviewKnowledgeObject } from "../../../lib/knowledgeViews.js";
import { RecallInspectSection } from "./RecallInspectSection.js";

interface MemoryViewerProps {
  config: Config;
  onClose: () => void;
}

type ReviewItem = KnowledgeObject & { review_kind: "procedure" | "action" | "artifact" };

export function MemoryViewer({ config, onClose }: MemoryViewerProps) {
  const [activeTab, setActiveTab] = useState<MemoryTabType>("overview");
  const [summary, setSummary] = useState<KnowledgeSummary | null>(null);
  const [reviewItems, setReviewItems] = useState<ReviewItem[] | null>(null);
  const [libraryItems, setLibraryItems] = useState<KnowledgeObject[] | null>(null);
  const [libraryType, setLibraryType] = useState<KnowledgeObjectType>("episode");
  const [recentSent, setRecentSent] = useState<KnowledgeObject[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const recallTab = useRecallInspectTab(config);

  async function load() {
    setError(null);
    try {
      const [nextSummary, procedures, actions, artifacts, sent, library] = await Promise.all([
        getKnowledgeSummary(config),
        listKnowledgeObjects(config, { object_type: "procedure_candidate", status: "draft" }),
        listKnowledgeObjects(config, { object_type: "action_candidate", status: "draft" }),
        listKnowledgeObjects(config, { object_type: "artifact", status: "draft" }),
        listKnowledgeObjects(config, { object_type: "outcome_feedback", limit: 5 }),
        listKnowledgeObjects(config, { object_type: libraryType, limit: 12 }),
      ]);
      setSummary(nextSummary);
      setReviewItems([
        ...procedures.objects.map((item) => ({ ...item, review_kind: "procedure" as const })),
        ...actions.objects.map((item) => ({ ...item, review_kind: "action" as const })),
        ...artifacts.objects.map((item) => ({ ...item, review_kind: "artifact" as const })),
      ].filter(shouldReviewKnowledgeObject));
      setLibraryItems(library.objects);
      setRecentSent(sent.objects.slice(0, 5));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    void load();
  }, []);

  useKeypress((key) => {
    if (key.name === "escape") {
      if (activeTab === "activation" && recallTab.inputActive) return;
      onClose();
      return;
    }
    if (key.name === "tab") {
      setActiveTab((current) => {
        const index = MEMORY_TABS.indexOf(current);
        return MEMORY_TABS[(index + 1) % MEMORY_TABS.length];
      });
      return;
    }
    if (Number.isInteger(Number(key.sequence))) {
      const index = Number(key.sequence) - 1;
      if (MEMORY_TABS[index]) setActiveTab(MEMORY_TABS[index]);
      return;
    }
    if (activeTab === "library") {
      const nextType = typeFromKey(key.sequence);
      if (nextType) {
        setLibraryType(nextType);
        void listKnowledgeObjects(config, { object_type: nextType, limit: 12 })
          .then((result) => setLibraryItems(result.objects))
          .catch((e) => setError(e instanceof Error ? e.message : String(e)));
      }
    }
    if (activeTab === "activation") recallTab.handleKeys(key);
  }, { isActive: true });

  return (
    <Dialog title="MEMORY" size="full" onClose={onClose}>
      {({ width, height }) => {
        const sectionHeight = Math.max(1, height - 5 - (error ? 1 : 0));
        const copy = MEMORY_TAB_COPY[activeTab];
        const status = activeTab === "activation"
          ? recallTab.result
            ? `${recallTab.result.candidates.length} activated · ${recallTab.result.omitted.length} omitted`
            : "no query yet"
          : `${reviewItems?.length ?? 0} review · ${summary?.surfaces.reduce((sum, surface) => sum + surface.count, 0) ?? 0} objects`;

        return (
          <>
            <box flexDirection="row" marginBottom={1} marginTop={1}>
              <Tabs
                tabs={MEMORY_TABS}
                activeTab={activeTab}
                onTabChange={setActiveTab}
                labels={memoryTabLabels(width)}
              />
            </box>

            <box flexDirection="row" marginBottom={1}>
              <box width={Math.max(20, Math.floor(width * 0.58))}>
                <text>
                  <span fg={colors.text.secondary}>{copy.title}</span>
                  <span fg={colors.text.disabled}> {"\u2502"} {truncateText(copy.description, Math.max(8, Math.floor(width * 0.58) - copy.title.length - 3))}</span>
                </text>
              </box>
              <box flexGrow={1} />
              <text><span fg={colors.text.disabled}>{truncateText(status, Math.max(0, Math.floor(width * 0.38)))}</span></text>
            </box>

            {error && (
              <box marginBottom={1}>
                <text><span fg={colors.status.error}>{truncateText(error, width)}</span></text>
              </box>
            )}

            {activeTab === "overview" && (
              <KnowledgeOverview
                summary={summary}
                reviewItems={reviewItems}
                recentSent={recentSent}
                height={sectionHeight}
                width={width}
              />
            )}
            {activeTab === "library" && (
              <KnowledgeLibrary
                summary={summary}
                items={libraryItems}
                activeType={libraryType}
                height={sectionHeight}
                width={width}
              />
            )}
            {activeTab === "review" && (
              <KnowledgeReview
                items={reviewItems}
                height={sectionHeight}
                width={width}
              />
            )}
            {activeTab === "activation" && (
              <RecallInspectSection tab={recallTab} height={sectionHeight} width={width} />
            )}
          </>
        );
      }}
    </Dialog>
  );
}

function typeFromKey(sequence: string | undefined): KnowledgeObjectType | null {
  const index = Number(sequence) - 1;
  if (!Number.isInteger(index)) return null;
  return KNOWLEDGE_LIBRARY_TYPES[index]?.type ?? null;
}

function KnowledgeOverview({
  summary,
  reviewItems,
  recentSent,
  height,
  width,
}: {
  summary: KnowledgeSummary | null;
  reviewItems: ReviewItem[] | null;
  recentSent: KnowledgeObject[] | null;
  height: number;
  width: number;
}) {
  const contentWidth = Math.max(20, width - 4);
  const lines: string[] = [];

  lines.push("COUNTS");
  if (!summary) {
    lines.push("loading");
  } else {
    for (const view of KNOWLEDGE_LIBRARY_TYPES) {
      lines.push(`${view.label.padEnd(12)} ${String(knowledgeSurfaceCount(summary.surfaces, view.type)).padStart(4)}  ${view.description}`);
    }
  }

  lines.push("", "NEEDS REVIEW");
  if (reviewItems === null) {
    lines.push("loading");
  } else if (reviewItems.length === 0) {
    lines.push("nothing needs review");
  } else {
    for (const item of reviewItems.slice(0, 8)) {
      lines.push(`${reviewKind(item)} · ${item.proactiveness_level} · ${truncateText(item.title, Math.max(12, contentWidth - 24))}`);
      lines.push(`  ${truncateText(item.text.replace(/\s+/g, " "), Math.max(12, contentWidth - 2))}`);
    }
  }

  lines.push("", "RECENT ACTIVATION");
  if (recentSent === null) {
    lines.push("loading");
  } else if (recentSent.length === 0) {
    lines.push("no activation records yet");
  } else {
    for (const item of recentSent) {
      lines.push(`${formatAge(item.updated_at)} · ${truncateText(item.text.replace(/\s+/g, " "), Math.max(12, contentWidth - 8))}`);
    }
  }
  return (
    <box flexDirection="column" width={width} height={height} paddingLeft={1} paddingRight={1} overflow="hidden">
      {lines.slice(0, height).map((line, index) => {
        const heading = line === line.toUpperCase() && line.length > 0;
        return (
          <text key={index}>
            <span fg={heading ? colors.text.secondary : colors.text.muted}>{truncateText(line || " ", contentWidth)}</span>
          </text>
        );
      })}
    </box>
  );
}

function KnowledgeLibrary({
  summary,
  items,
  activeType,
  height,
  width,
}: {
  summary: KnowledgeSummary | null;
  items: KnowledgeObject[] | null;
  activeType: KnowledgeObjectType;
  height: number;
  width: number;
}) {
  const contentWidth = Math.max(20, width - 4);
  const lines: string[] = [];

  lines.push("TYPES");
  for (const [index, view] of KNOWLEDGE_LIBRARY_TYPES.entries()) {
    const marker = view.type === activeType ? ">" : " ";
    const count = summary ? knowledgeSurfaceCount(summary.surfaces, view.type) : 0;
    lines.push(`${marker} ${index + 1}. ${view.label.padEnd(12)} ${String(count).padStart(4)}  ${view.description}`);
  }

  lines.push("", activeType.toUpperCase());
  if (items === null) {
    lines.push("loading");
  } else if (items.length === 0) {
    lines.push("no objects");
  } else {
    for (const item of items) {
      lines.push(`${formatAge(item.updated_at)} · ${item.status} · ${truncateText(item.title, Math.max(12, contentWidth - 22))}`);
      lines.push(`  ${truncateText(item.text.replace(/\s+/g, " "), Math.max(12, contentWidth - 2))}`);
    }
  }

  return <Lines lines={lines} height={height} width={width} />;
}

function KnowledgeReview({
  items,
  height,
  width,
}: {
  items: ReviewItem[] | null;
  height: number;
  width: number;
}) {
  const contentWidth = Math.max(20, width - 4);
  const lines: string[] = ["DRAFT DECISIONS"];

  if (items === null) {
    lines.push("loading");
  } else if (items.length === 0) {
    lines.push("nothing needs review");
  } else {
    for (const item of items) {
      lines.push(`${reviewKind(item)} · ${item.proactiveness_level} · ${item.status} · ${truncateText(item.title, Math.max(12, contentWidth - 30))}`);
      lines.push(`  ${truncateText(item.text.replace(/\s+/g, " "), Math.max(12, contentWidth - 2))}`);
    }
  }

  return <Lines lines={lines} height={height} width={width} />;
}

function Lines({ lines, height, width }: { lines: string[]; height: number; width: number }) {
  const contentWidth = Math.max(20, width - 4);
  return (
    <box flexDirection="column" width={width} height={height} paddingLeft={1} paddingRight={1} overflow="hidden">
      {lines.slice(0, height).map((line, index) => {
        const heading = line === line.toUpperCase() && line.length > 0;
        return (
          <text key={index}>
            <span fg={heading ? colors.text.secondary : colors.text.muted}>{truncateText(line || " ", contentWidth)}</span>
          </text>
        );
      })}
    </box>
  );
}
