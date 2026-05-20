import { useState } from "react";
import { X } from "lucide-react";
import clsx from "clsx";
import { useStore } from "../store";
import { MEMORY_TABS, type MemoryTab } from "../lib/memoryTabs";
import { PageModal } from "./PageModal";
import { RecallPane } from "./memory/RecallPane";
import { KnowledgeHomePane } from "./memory/KnowledgeHomePane";
import { KnowledgeLibraryPane } from "./memory/KnowledgeLibraryPane";
import { KnowledgeReviewPane } from "./memory/KnowledgeReviewPane";
import { ICON } from "../lib/icons";

export function MemoryModal() {
  const open = useStore((s) => s.memoryOpen);
  const close = useStore((s) => s.closeMemory);
  const [tab, setTab] = useState<MemoryTab>("overview");

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

      <nav className="relative z-10 flex flex-wrap items-end gap-4 mx-6 mt-3 overflow-visible">
        {MEMORY_TABS.map((t) => (
          <TabButton
            key={t.id}
            label={t.label}
            active={tab === t.id}
            onClick={() => setTab(t.id)}
          />
        ))}
      </nav>

      <div className="h-full overflow-hidden">
        {tab === "overview" && (
          <KnowledgeHomePane
            onOpenLibrary={() => setTab("library")}
            onOpenReview={() => setTab("review")}
            onOpenActivation={() => setTab("activation")}
          />
        )}
        <section className={clsx("h-full", tab === "library" ? "block" : "hidden")}>
          <KnowledgeLibraryPane />
        </section>
        <section className={clsx("h-full", tab === "review" ? "block" : "hidden")}>
          <KnowledgeReviewPane />
        </section>
        <section className={clsx("h-full", tab === "activation" ? "block" : "hidden")}>
          <RecallPane />
        </section>
      </div>
    </PageModal>
  );
}

function TabButton({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
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
