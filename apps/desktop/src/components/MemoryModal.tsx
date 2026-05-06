import { useEffect, useRef, useState } from "react";
import { ChevronDown, X } from "lucide-react";
import clsx from "clsx";
import { useStore } from "../store";
import type { Fact, Observation } from "../api";
import { PageModal } from "./PageModal";
import { FactsPane } from "./memory/FactsPane";
import { ObservationsPane } from "./memory/ObservationsPane";
import { RecallPane } from "./memory/RecallPane";
import { SentPane } from "./memory/SentPane";
import { CleanupPane } from "./memory/CleanupPane";
import { AuditPane } from "./memory/AuditPane";

type Tab = "search" | "facts" | "patterns" | "sent" | "cleanup" | "audit";

const PRIMARY_TABS: { id: Tab; label: string }[] = [
  { id: "search", label: "Search" },
  { id: "facts", label: "Facts" },
  { id: "patterns", label: "Patterns" },
];

const ADVANCED_TABS: { id: Tab; label: string }[] = [
  { id: "sent", label: "Sent" },
  { id: "cleanup", label: "Cleanup" },
  { id: "audit", label: "Audit" },
];

export function MemoryModal() {
  const open = useStore((s) => s.memoryOpen);
  const close = useStore((s) => s.closeMemory);
  const [tab, setTab] = useState<Tab>("search");
  const [targetFact, setTargetFact] = useState<Fact | null>(null);
  const [targetPatternId, setTargetPatternId] = useState<number | null>(null);

  const openFact = (fact: Fact) => {
    setTargetFact(fact);
    setTab("facts");
  };

  const openPattern = (pattern: Observation | number) => {
    setTargetPatternId(typeof pattern === "number" ? pattern : pattern.id);
    setTab("patterns");
  };

  return (
    <PageModal
      open={open}
      onClose={close}
      size="w-[min(1180px,calc(100vw-64px))] h-[min(760px,calc(100vh-64px))]"
      grid="grid-rows-[auto_auto_minmax(0,1fr)]"
    >
      <header className="flex items-center justify-between gap-3 pl-6 pr-3 pt-5">
        <h2 className="m-0 text-[18px] font-semibold tracking-[-0.014em] text-ink">Memory</h2>
        <button
          type="button"
          onClick={close}
          aria-label="Close"
          className="grid place-items-center w-7 h-7 rounded-md text-muted hover:bg-surface-soft hover:text-ink transition-colors"
        >
          <X size={13} strokeWidth={1.7} />
        </button>
      </header>

      <nav className="relative z-10 flex flex-wrap items-end gap-4 mx-6 mt-3 overflow-visible border-b border-line-soft">
        {PRIMARY_TABS.map((t) => (
          <TabButton
            key={t.id}
            label={t.label}
            active={tab === t.id}
            onClick={() => setTab(t.id)}
          />
        ))}
        <AdvancedMenu activeTab={tab} onSelect={setTab} />
      </nav>

      <div className="overflow-hidden">
        {tab === "search" && <RecallPane onOpenFact={openFact} onOpenPattern={openPattern} />}
        {tab === "sent" && <SentPane onOpenFact={openFact} onOpenPattern={openPattern} />}
        {tab === "facts" && <FactsPane targetFact={targetFact} />}
        {tab === "patterns" && <ObservationsPane targetPatternId={targetPatternId} onOpenFact={openFact} />}
        {tab === "cleanup" && <CleanupPane onOpenPattern={openPattern} />}
        {tab === "audit" && <AuditPane />}
      </div>
    </PageModal>
  );
}

function AdvancedMenu({ activeTab, onSelect }: { activeTab: Tab; onSelect: (tab: Tab) => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const active = ADVANCED_TABS.some((tab) => tab.id === activeTab);
  const activeLabel = ADVANCED_TABS.find((tab) => tab.id === activeTab)?.label;

  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative pb-2 -mb-px">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className={clsx(
          "inline-flex items-center gap-1 text-[13px] font-medium tracking-[-0.005em] transition-colors",
          active ? "text-ink" : "text-muted hover:text-ink",
        )}
      >
        {activeLabel ? `Advanced: ${activeLabel}` : "Advanced"}
        <ChevronDown size={12} strokeWidth={1.8} className={clsx("transition-transform", open && "rotate-180")} />
      </button>
      {active && <span className="absolute left-0 right-0 bottom-0 h-[2px] rounded-full bg-ink" />}
      {open && (
        <div className="absolute left-0 top-full z-20 mt-1 w-[150px] rounded-[8px] border border-line-soft bg-surface py-1 shadow-[var(--shadow-pop)]">
          {ADVANCED_TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => {
                onSelect(tab.id);
                setOpen(false);
              }}
              className={clsx(
                "block w-full px-3 py-1.5 text-left text-[12px] transition-colors",
                activeTab === tab.id ? "font-medium text-ink" : "text-ink-soft hover:bg-surface-soft hover:text-ink",
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
      )}
    </div>
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
        "relative pb-2 -mb-px text-[13px] font-medium tracking-[-0.005em] transition-colors",
        active ? "text-ink" : "text-muted hover:text-ink",
      )}
    >
      {label}
      {active && <span className="absolute left-0 right-0 bottom-0 h-[2px] rounded-full bg-ink" />}
    </button>
  );
}
