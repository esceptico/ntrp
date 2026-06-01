import { useState } from "react";

import { useStore } from "../store";
import { LearningsPane } from "./memory/LearningsPane";
import { MemoryItemsPane } from "./memory/MemoryItemsPane";
import { PageModal } from "./PageModal";
import { Tab, Tabs } from "./ui/Tabs";
import { TabPanels, useTabDirection } from "./ui/TabPanels";

type View = "memory" | "learnings";

const VIEWS: { id: View; label: string }[] = [
  { id: "memory", label: "Memory" },
  { id: "learnings", label: "Learnings" },
];
const VIEW_IDS = VIEWS.map((v) => v.id);

export function MemoryModal() {
  const open = useStore((s) => s.memoryOpen);
  const close = useStore((s) => s.closeMemory);
  const [view, setView] = useState<View>("memory");
  const direction = useTabDirection(VIEW_IDS, view);

  const toggle = (
    <Tabs
      value={view}
      onChange={(v) => setView(v as View)}
      variant="pill"
      className="items-center gap-0.5 rounded-lg bg-surface-soft p-0.5"
      indicatorClassName="bg-surface shadow-[0_1px_2px_rgba(0,0,0,0.06)]"
    >
      {VIEWS.map((v) => (
        <Tab
          key={v.id}
          value={v.id}
          className="rounded-md px-3 py-1 text-sm font-medium text-muted transition-colors hover:text-ink data-[active=true]:text-ink"
        >
          {v.label}
        </Tab>
      ))}
    </Tabs>
  );

  return (
    <PageModal
      open={open}
      onClose={close}
      header={{ title: "Memory", actions: toggle }}
      size="w-[min(1280px,calc(100vw-32px))] h-[min(820px,calc(100vh-32px))] sm:w-[min(1280px,calc(100vw-80px))] sm:h-[min(820px,calc(100vh-80px))]"
    >
      <TabPanels value={view} direction={direction} className="h-full min-h-0 overflow-hidden">
        {view === "memory" ? <MemoryItemsPane /> : <LearningsPane />}
      </TabPanels>
    </PageModal>
  );
}
