import { useState } from "react";
import { X } from "lucide-react";
import clsx from "clsx";
import { useStore } from "../store";
import { PageModal } from "./PageModal";
import { FactsPane } from "./memory/FactsPane";
import { ObservationsPane } from "./memory/ObservationsPane";
import { DreamsPane } from "./memory/DreamsPane";
import { ProfilePane } from "./memory/ProfilePane";
import { MergesPane } from "./memory/MergesPane";

type Tab = "facts" | "observations" | "profile" | "dreams" | "merges";

const TABS: { id: Tab; label: string }[] = [
  { id: "facts", label: "Facts" },
  { id: "observations", label: "Observations" },
  { id: "profile", label: "Profile" },
  { id: "dreams", label: "Dreams" },
  { id: "merges", label: "Merges" },
];

export function MemoryModal() {
  const open = useStore((s) => s.memoryOpen);
  const close = useStore((s) => s.closeMemory);
  const [tab, setTab] = useState<Tab>("facts");

  return (
    <PageModal open={open} onClose={close} grid="grid-rows-[auto_auto_minmax(0,1fr)]">
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

      <nav className="flex items-end gap-5 mx-6 mt-3 border-b border-line-soft">
        {TABS.map((t) => (
          <TabButton
            key={t.id}
            label={t.label}
            active={tab === t.id}
            onClick={() => setTab(t.id)}
          />
        ))}
      </nav>

      <div className="overflow-hidden">
        {tab === "facts" && <FactsPane />}
        {tab === "observations" && <ObservationsPane />}
        {tab === "profile" && <ProfilePane />}
        {tab === "dreams" && <DreamsPane />}
        {tab === "merges" && <MergesPane />}
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
        "relative pb-2 -mb-px text-[13px] font-medium tracking-[-0.005em] transition-colors",
        active ? "text-ink" : "text-muted hover:text-ink",
      )}
    >
      {label}
      {active && <span className="absolute left-0 right-0 bottom-0 h-[2px] rounded-full bg-ink" />}
    </button>
  );
}
