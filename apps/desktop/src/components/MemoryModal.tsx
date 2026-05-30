import { useState } from "react";

import { useStore } from "../store";
import { LearningsPane } from "./memory/LearningsPane";
import { MemoryItemsPane } from "./memory/MemoryItemsPane";
import { PageModal } from "./PageModal";

type View = "memory" | "learnings";

const VIEWS: { id: View; label: string }[] = [
  { id: "memory", label: "Memory" },
  { id: "learnings", label: "Learnings" },
];

export function MemoryModal() {
  const open = useStore((s) => s.memoryOpen);
  const close = useStore((s) => s.closeMemory);
  const [view, setView] = useState<View>("memory");

  const toggle = (
    <div className="flex items-center gap-0.5 rounded-lg bg-surface-soft p-0.5">
      {VIEWS.map((v) => (
        <button
          key={v.id}
          type="button"
          onClick={() => setView(v.id)}
          className={[
            "rounded-md px-3 py-1 text-sm font-medium transition-colors",
            view === v.id ? "bg-surface text-ink shadow-[0_1px_2px_rgba(0,0,0,0.06)]" : "text-muted hover:text-ink",
          ].join(" ")}
        >
          {v.label}
        </button>
      ))}
    </div>
  );

  return (
    <PageModal
      open={open}
      onClose={close}
      header={{ title: "Memory", actions: toggle }}
      size="w-[min(1280px,calc(100vw-32px))] h-[min(820px,calc(100vh-32px))] sm:w-[min(1280px,calc(100vw-80px))] sm:h-[min(820px,calc(100vh-80px))]"
    >
      {view === "memory" ? <MemoryItemsPane /> : <LearningsPane />}
    </PageModal>
  );
}
