import { useEffect, useState } from "react";
import type { Config } from "../../../types.js";
import {
  getMemoryStats,
  listMemoryItems,
  type MemoryItem,
  type MemoryItemKind,
  type MemoryStats,
} from "../../../api/client.js";
import { useKeypress } from "../../../hooks/useKeypress.js";
import { MEMORY_TAB_COPY, MEMORY_TABS, memoryTabLabels, type MemoryTabType } from "../../../lib/memoryTabs.js";
import { formatAge } from "../../../lib/utils.js";
import { Dialog, Tabs, colors, truncateText } from "../../ui/index.js";

interface MemoryViewerProps {
  config: Config;
  onClose: () => void;
}

const MEMORY_KINDS: MemoryItemKind[] = ["episode", "observation", "claim", "skill", "proposal", "artifact_ref"];

export function MemoryViewer({ config, onClose }: MemoryViewerProps) {
  const [activeTab, setActiveTab] = useState<MemoryTabType>("today");
  const [stats, setStats] = useState<MemoryStats | null>(null);
  const [items, setItems] = useState<MemoryItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [kind, setKind] = useState<MemoryItemKind>("episode");
  const [error, setError] = useState<string | null>(null);

  async function load(nextKind = kind) {
    setError(null);
    try {
      const [nextStats, page] = await Promise.all([
        getMemoryStats(config),
        listMemoryItems(config, { kinds: [nextKind], statuses: ["active"], limit: 12 }),
      ]);
      setStats(nextStats);
      setItems(page.items);
      setTotal(page.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    void load();
  }, []);

  useKeypress((key) => {
    if (key.name === "escape") {
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
      if (activeTab === "search" && MEMORY_KINDS[index]) {
        const nextKind = MEMORY_KINDS[index];
        setKind(nextKind);
        void load(nextKind);
        return;
      }
      if (MEMORY_TABS[index]) setActiveTab(MEMORY_TABS[index]);
    }
  }, { isActive: true });

  return (
    <Dialog title="MEMORY" size="full" onClose={onClose}>
      {({ width, height }) => {
        const sectionHeight = Math.max(1, height - 5 - (error ? 1 : 0));
        const copy = MEMORY_TAB_COPY[activeTab];
        const status = stats
          ? `${stats.counts.claim?.active ?? 0} claims · ${stats.counts.observation?.active ?? 0} observations`
          : "loading";

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
                  <span fg={colors.text.disabled}> {"|"} {truncateText(copy.description, Math.max(8, Math.floor(width * 0.58) - copy.title.length - 3))}</span>
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

            {activeTab === "today" && <MemoryOverview stats={stats} height={sectionHeight} width={width} />}
            {activeTab === "graph" && (
              <MemoryStaticPanel
                title="GRAPH"
                lines={["Desktop renders the real provenance DAG from /admin/memory/items/:id/graph.", "TUI navigation is keyboard-only for now; use Search to pick ids."]}
                height={sectionHeight}
                width={width}
              />
            )}
            {activeTab === "skills" && (
              <MemoryStaticPanel
                title="SKILLS"
                lines={["Skills are memory_items.kind=skill with evidence parents and source_refs to skill files.", "Desktop exposes enable/archive actions via /admin/memory/skills."]}
                height={sectionHeight}
                width={width}
              />
            )}
            {activeTab === "search" && (
              <MemoryItems items={items} total={total} activeKind={kind} height={sectionHeight} width={width} />
            )}
          </>
        );
      }}
    </Dialog>
  );
}

function MemoryStaticPanel({ title, lines, height, width }: { title: string; lines: string[]; height: number; width: number }) {
  const contentWidth = Math.max(20, width - 4);
  const visible = [title, "", ...lines].slice(0, Math.max(1, height - 2));
  return (
    <box flexDirection="column" height={height}>
      {visible.map((line, index) => (
        <text key={index}>
          <span fg={index === 0 ? colors.text.primary : colors.text.secondary}>
            {truncateText(line, contentWidth)}
          </span>
        </text>
      ))}
    </box>
  );
}

function MemoryOverview({ stats, height, width }: { stats: MemoryStats | null; height: number; width: number }) {
  const contentWidth = Math.max(20, width - 4);
  const lines: string[] = ["COUNTS"];
  if (!stats) {
    lines.push("loading");
  } else {
    for (const kind of MEMORY_KINDS) {
      const counts = stats.counts[kind] ?? { active: 0, superseded: 0, archived: 0 };
      lines.push(
        `${kind.padEnd(12)} ${String(counts.active ?? 0).padStart(4)} active  ${String(counts.superseded ?? 0).padStart(4)} superseded  ${String(counts.archived ?? 0).padStart(4)} archived`,
      );
    }
  }
  lines.push("", "Press tab for item lists. In Items, keys 1-6 switch kind.");

  return <TextLines lines={lines} height={height} width={contentWidth} />;
}

function MemoryItems({
  items,
  total,
  activeKind,
  height,
  width,
}: {
  items: MemoryItem[] | null;
  total: number;
  activeKind: MemoryItemKind;
  height: number;
  width: number;
}) {
  const contentWidth = Math.max(20, width - 4);
  const lines: string[] = [
    MEMORY_KINDS.map((kind, index) => `${index + 1}:${kind}${kind === activeKind ? "*" : ""}`).join("  "),
    "",
  ];

  if (items === null) {
    lines.push("loading");
  } else if (items.length === 0) {
    lines.push(`No active ${activeKind} items.`);
  } else {
    lines.push(`${items.length}/${total} active ${activeKind}`);
    for (const item of items) {
      const updated = item.updated_at ? formatAge(item.updated_at) : "unknown";
      lines.push(`${updated} · ${item.status} · ${truncateText(item.content.replace(/\s+/g, " "), contentWidth - 18)}`);
      if (item.tags.length) lines.push(`  tags: ${truncateText(item.tags.join(", "), contentWidth - 8)}`);
    }
  }

  return <TextLines lines={lines} height={height} width={contentWidth} />;
}

function TextLines({ lines, height, width }: { lines: string[]; height: number; width: number }) {
  return (
    <box flexDirection="column" height={height}>
      {lines.slice(0, height).map((line, index) => (
        <text key={`${index}-${line}`}>
          <span fg={line === "" ? colors.text.disabled : colors.text.primary}>{truncateText(line, width)}</span>
        </text>
      ))}
    </box>
  );
}
