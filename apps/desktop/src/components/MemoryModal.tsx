import { useState } from "react";
import { ChevronRight, X } from "lucide-react";
import clsx from "clsx";
import { useStore } from "../store";
import type { Fact, Observation } from "../api";
import { switchSession } from "../actions";
import type { FactChatSourceFocus } from "../lib/memoryProvenance";
import { resolveMessageSourceFocus } from "../lib/messageSourceFocus";
import { advancedMemoryTabsVisible, isAdvancedMemoryTab, type MemoryTab } from "../lib/memoryTabs";
import { nextMemoryTarget, type MemoryTarget } from "../lib/memoryTargets";
import { PageModal } from "./PageModal";
import { FactsPane } from "./memory/FactsPane";
import { ObservationsPane } from "./memory/ObservationsPane";
import { RecallPane } from "./memory/RecallPane";
import { SentPane } from "./memory/SentPane";
import { CleanupPane } from "./memory/CleanupPane";
import { AuditPane } from "./memory/AuditPane";
import { ICON } from "../lib/icons";

const PRIMARY_TABS: { id: MemoryTab; label: string }[] = [
  { id: "search", label: "Search" },
  { id: "facts", label: "Facts" },
  { id: "patterns", label: "Patterns" },
];

const ADVANCED_TABS: { id: MemoryTab; label: string }[] = [
  { id: "sent", label: "Sent" },
  { id: "cleanup", label: "Cleanup" },
  { id: "audit", label: "Audit" },
];

export function MemoryModal() {
  const open = useStore((s) => s.memoryOpen);
  const close = useStore((s) => s.closeMemory);
  const setSourceFocus = useStore((s) => s.setSourceFocus);
  const [tab, setTab] = useState<MemoryTab>("search");
  const [targetFact, setTargetFact] = useState<MemoryTarget<Fact | number> | null>(null);
  const [targetPattern, setTargetPattern] = useState<MemoryTarget<Observation | number> | null>(null);

  const openFact = (fact: Fact | number) => {
    setTargetFact((current) => nextMemoryTarget(current, fact));
    setTab("facts");
  };

  const openPattern = (pattern: Observation | number) => {
    setTargetPattern((current) => nextMemoryTarget(current, pattern));
    setTab("patterns");
  };

  const openSourceSession = async (focus: FactChatSourceFocus) => {
    await switchSession(focus.sessionId, {
      around: focus.messageStartId,
      aroundSeq: focus.messageStart,
    });
    const state = useStore.getState();
    const nextFocus = resolveMessageSourceFocus(
      state.order,
      state.messages,
      { ...focus, nonce: Date.now() },
      state.currentSessionId,
    );
    setSourceFocus(nextFocus);
    close();
  };

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

      <nav className="relative z-10 flex flex-wrap items-end gap-4 mx-6 mt-3 overflow-visible border-b border-line-soft">
        {PRIMARY_TABS.map((t) => (
          <TabButton
            key={t.id}
            label={t.label}
            active={tab === t.id}
            onClick={() => setTab(t.id)}
          />
        ))}
        <AdvancedRow activeTab={tab} onSelect={setTab} />
      </nav>

      <div className="h-full overflow-hidden">
        <section className={clsx("h-full", tab === "search" ? "block" : "hidden")}>
          <RecallPane onOpenFact={openFact} onOpenPattern={openPattern} />
        </section>
        {tab === "sent" && <SentPane onOpenFact={openFact} onOpenPattern={openPattern} />}
        {tab === "facts" && (
          <FactsPane
            targetFact={targetFact}
            onOpenSource={(sessionId) => void openSourceSession(sessionId)}
          />
        )}
        {tab === "patterns" && (
          <ObservationsPane
            targetPattern={targetPattern}
            onOpenFact={openFact}
            onOpenSource={(focus) => void openSourceSession(focus)}
          />
        )}
        {tab === "cleanup" && <CleanupPane onOpenFact={openFact} onOpenPattern={openPattern} />}
        {tab === "audit" && <AuditPane />}
      </div>
    </PageModal>
  );
}

function AdvancedRow({ activeTab, onSelect }: { activeTab: MemoryTab; onSelect: (tab: MemoryTab) => void }) {
  const [expanded, setExpanded] = useState(false);
  const visible = advancedMemoryTabsVisible(activeTab, expanded);
  const active = isAdvancedMemoryTab(activeTab);

  return (
    <div
      className={clsx(
        "mb-1 flex h-7 items-center overflow-hidden rounded-full border px-1 transition-colors duration-200",
        active ? "border-line-strong bg-surface-soft" : "border-line-soft bg-surface-soft/60",
      )}
    >
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={visible}
        className={clsx(
          "inline-flex h-5.5 items-center gap-1 rounded-full px-2 text-sm font-medium tracking-[-0.005em] transition-colors duration-150",
          active ? "bg-surface text-ink" : "text-muted hover:bg-surface hover:text-ink",
        )}
      >
        Advanced
        <ChevronRight
          size={ICON.XS}
          strokeWidth={2}
          className={clsx("transition-transform duration-200 ease-out", visible && "rotate-90")}
        />
      </button>
      {/* max-width is still D-tier here, but dropping margin-left from
          the transition list spares one layout property; the 4px ml
          change snaps visually-invisibly behind the opacity fade. The
          chevron sibling does NOT shift because the section's width is
          still animated by max-width. */}
      <div
        className={clsx(
          "flex items-center gap-1 overflow-hidden transition-[max-width,opacity] duration-200 ease-out",
          visible ? "ml-1 max-w-[260px] opacity-100" : "ml-0 max-w-0 opacity-0 pointer-events-none",
        )}
        aria-hidden={!visible}
      >
        {ADVANCED_TABS.map((tab) => (
          <PillTabButton
            key={tab.id}
            label={tab.label}
            active={activeTab === tab.id}
            onClick={() => onSelect(tab.id)}
            focusable={visible}
          />
        ))}
      </div>
    </div>
  );
}

function PillTabButton({
  label,
  active,
  onClick,
  focusable,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  focusable: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      tabIndex={focusable ? undefined : -1}
      className={clsx(
        "h-5.5 whitespace-nowrap rounded-full px-2 text-sm font-medium tracking-[-0.005em] transition-colors duration-150",
        active ? "bg-surface text-ink shadow-[0_0_0_1px_var(--color-line-soft)]" : "text-muted hover:bg-surface hover:text-ink",
      )}
    >
      {label}
    </button>
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
