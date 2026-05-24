import { useState } from "react";
import type { KeyboardEvent } from "react";
import { X } from "lucide-react";
import clsx from "clsx";
import { useStore } from "../store";
import { MEMORY_TABS, type MemoryTab } from "../lib/memoryTabs";
import { PageModal } from "./PageModal";
import { RecallPane } from "./memory/RecallPane";
import { KnowledgeHomePane } from "./memory/KnowledgeHomePane";
import { KnowledgeLibraryPane, type LibraryTypeFilter } from "./memory/KnowledgeLibraryPane";
import { KnowledgeReviewPane } from "./memory/KnowledgeReviewPane";
import { ICON } from "../lib/icons";

export function MemoryModal() {
  const open = useStore((s) => s.memoryOpen);
  const close = useStore((s) => s.closeMemory);
  const [tab, setTab] = useState<MemoryTab>("overview");
  const [libraryInitialType, setLibraryInitialType] = useState<LibraryTypeFilter>("fact");
  const [libraryFocusVersion, setLibraryFocusVersion] = useState(0);

  function openLibrary(type: LibraryTypeFilter = "all") {
    setLibraryInitialType(type);
    setLibraryFocusVersion((current) => current + 1);
    setTab("library");
  }

  function focusTab(nextTab: MemoryTab) {
    setTab(nextTab);
    window.requestAnimationFrame(() => document.getElementById(`memory-tab-${nextTab}`)?.focus());
  }

  function handleTabKeyDown(event: KeyboardEvent<HTMLButtonElement>, currentTab: MemoryTab) {
    const currentIndex = MEMORY_TABS.findIndex((candidate) => candidate.id === currentTab);
    if (currentIndex === -1) return;

    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      event.preventDefault();
      focusTab(MEMORY_TABS[(currentIndex + 1) % MEMORY_TABS.length].id);
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      event.preventDefault();
      focusTab(MEMORY_TABS[(currentIndex - 1 + MEMORY_TABS.length) % MEMORY_TABS.length].id);
    } else if (event.key === "Home") {
      event.preventDefault();
      focusTab(MEMORY_TABS[0].id);
    } else if (event.key === "End") {
      event.preventDefault();
      focusTab(MEMORY_TABS[MEMORY_TABS.length - 1].id);
    }
  }

  return (
    <PageModal
      open={open}
      onClose={close}
      size="w-[min(1180px,calc(100vw-32px))] h-[min(760px,calc(100vh-32px))] sm:w-[min(1180px,calc(100vw-64px))] sm:h-[min(760px,calc(100vh-64px))]"
      grid="grid-rows-[auto_auto_minmax(0,1fr)]"
    >
      <header className="flex items-center justify-between gap-3 pl-6 pr-3 pt-5">
        <h2 className="m-0 text-xl font-semibold tracking-[-0.014em] text-ink">Memory</h2>
        <button
          type="button"
          onClick={close}
          aria-label="Close"
          className="grid place-items-center w-7 h-7 rounded-md text-muted hover:bg-surface-soft hover:text-ink transition-colors"
        >
          <X size={ICON.SM} strokeWidth={2} />
        </button>
      </header>

      <nav aria-label="Memory sections" role="tablist" className="relative z-10 flex flex-wrap items-end gap-4 mx-6 mt-3 overflow-visible">
        {MEMORY_TABS.map((t) => (
          <TabButton
            key={t.id}
            id={`memory-tab-${t.id}`}
            panelId={`memory-panel-${t.id}`}
            label={t.label}
            active={tab === t.id}
            onClick={() => setTab(t.id)}
            onKeyDown={(event) => handleTabKeyDown(event, t.id)}
          />
        ))}
      </nav>

      <div className="h-full overflow-hidden">
        {tab === "overview" && (
          <section id="memory-panel-overview" role="tabpanel" aria-labelledby="memory-tab-overview" className="h-full">
            <KnowledgeHomePane
              onOpenLibrary={openLibrary}
              onOpenReview={() => setTab("review")}
              onOpenActivation={() => setTab("activation")}
            />
          </section>
        )}
        <section
          id="memory-panel-library"
          role="tabpanel"
          aria-labelledby="memory-tab-library"
          className={clsx("h-full", tab === "library" ? "block" : "hidden")}
        >
          <KnowledgeLibraryPane initialType={libraryInitialType} focusVersion={libraryFocusVersion} />
        </section>
        <section
          id="memory-panel-review"
          role="tabpanel"
          aria-labelledby="memory-tab-review"
          className={clsx("h-full", tab === "review" ? "block" : "hidden")}
        >
          <KnowledgeReviewPane />
        </section>
        <section
          id="memory-panel-activation"
          role="tabpanel"
          aria-labelledby="memory-tab-activation"
          className={clsx("h-full", tab === "activation" ? "block" : "hidden")}
        >
          <RecallPane />
        </section>
      </div>
    </PageModal>
  );
}

function TabButton({
  id,
  panelId,
  label,
  active,
  onClick,
  onKeyDown,
}: {
  id: string;
  panelId: string;
  label: string;
  active: boolean;
  onClick: () => void;
  onKeyDown: (event: KeyboardEvent<HTMLButtonElement>) => void;
}) {
  return (
    <button
      id={id}
      type="button"
      role="tab"
      aria-controls={panelId}
      aria-selected={active}
      tabIndex={active ? 0 : -1}
      onClick={onClick}
      onKeyDown={onKeyDown}
      className={clsx(
        "relative pb-2 -mb-px text-base font-medium tracking-[-0.005em] transition-colors",
        active ? "text-ink" : "text-muted hover:text-ink",
      )}
    >
      {label}
      {active && <span className="absolute left-0 right-0 bottom-0 h-[2px] rounded-full bg-ink" />}
    </button>
  );
}
