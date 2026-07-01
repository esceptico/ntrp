import { FileText } from "lucide-react";
import { Markdown } from "@/components/ui/Markdown";
import { WikiLinkContext, type WikiLinkHandlers } from "@/lib/wikilink";
import { TabPanels } from "@/components/ui/TabPanels";
import { DetailPlaceholder } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { DetailShell } from "@/components/ui/DetailShell";
import { ListError } from "@/components/ui/ListColumn";
import { MetaGrid } from "@/components/ui/MetaGrid";
import { Pill } from "@/components/ui/Pill";
import { Properties } from "@/features/memory/components/shared";
import { displayTitle, isRecordListPage, stripCites, stripLeadingH1 } from "@/features/memory/lib/format";
import { TimelineDisclosure } from "@/features/memory/components/MemoryTimelineDisclosure";
import { CopyPath } from "@/features/memory/components/CopyPath";
import type { MemoryArtifact } from "@/api/memoryArtifacts";

export function FileDetailPane({
  active,
  loading,
  direction,
  contentNotice,
  contentError,
  contentLoading,
  wikiHandlers,
  onRetry,
}: {
  active: MemoryArtifact | null;
  loading: boolean;
  direction: number;
  contentNotice: string | null;
  contentError: string | null;
  contentLoading: boolean;
  wikiHandlers: WikiLinkHandlers;
  onRetry: () => void;
}) {
  if (!active) {
    return loading ? (
      <DetailPlaceholder>Loading…</DetailPlaceholder>
    ) : (
      <DetailPlaceholder icon={FileText} hint="Pick a note from the list to read it.">
        Nothing selected
      </DetailPlaceholder>
    );
  }
  return (
    <TabPanels
      value={active.path}
      direction={direction}
      className="h-full min-h-0 grid-rows-[minmax(0,1fr)] overflow-hidden"
    >
    <DetailShell
      header={
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-2xl font-medium tracking-tight text-ink truncate">{displayTitle(active)}</h1>
            <div className="mt-1 font-mono text-xs text-muted break-all">{active.path}</div>
          </div>
          <CopyPath path={active.path} />
        </div>
      }
      body={
        <>
          {active.readonly_reason && (
            <div className="mb-4 rounded-[10px] bg-surface-soft px-3 py-2 text-sm text-muted">
              {active.readonly_reason}
            </div>
          )}
          {contentNotice && (
            <div className="mb-4 rounded-[10px] bg-surface-soft px-3 py-2 text-sm text-muted">
              {contentNotice}
            </div>
          )}
          {contentError && !active.content ? (
            <ListError
              title="Couldn't load this note"
              message={contentError}
              onRetry={onRetry}
            />
          ) : contentLoading && !active.content ? (
            <div className="grid gap-2.5" role="status" aria-label="Loading artifact…">
              <Skeleton width="35%" height={14} />
              <Skeleton lines={8} height={13} />
            </div>
          ) : (
            <WikiLinkContext.Provider value={wikiHandlers}>
              <Properties frontmatter={active.frontmatter} />
              <Markdown content={stripLeadingH1(stripCites(active.content))} className="max-w-none" />
              {/* Record-list pages (directives/lessons/references/insights) already render
                  their records as the body — don't repeat them in the timeline disclosure. */}
              {!isRecordListPage(active.path) && <TimelineDisclosure timeline={active.timeline} />}
            </WikiLinkContext.Provider>
          )}
        </>
      }
      meta={
        <MetaGrid
          rows={[
            // record count lives in the Timeline disclosure header — don't repeat it here
            !!active.source && { label: "Source", value: active.source! },
            !active.editable && { label: "Access", value: "read-only" },
          ]}
        />
      }
      actions={
        active.labels.length > 0 ? (
          <div className="mr-auto flex flex-wrap items-center gap-1">
            {active.labels.map((label) => (
              <Pill key={label} tone="neutral">
                {label}
              </Pill>
            ))}
          </div>
        ) : null
      }
    />
    </TabPanels>
  );
}
