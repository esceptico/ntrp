import { useState } from "react";
import { useStore } from "../store";
import { MemoryPane, MEMORY_TABS, type MemoryDestination } from "./memory/MemoryPane";
import { Tab, Tabs } from "./ui/Tabs";
import { PageModal } from "./PageModal";

/** Memory views host. Title-row header with an inset-border tab strip below;
 *  the three destinations (Claims · Lenses · Graph) are one woven sheet, swapped
 *  by the shared-element pill indicator. Claims is home — claims ARE the memory;
 *  lenses are a view layer over them. */
export function MemoryModal() {
  const open = useStore((s) => s.memoryOpen);
  const close = useStore((s) => s.closeMemory);
  const [tab, setTab] = useState<MemoryDestination>("claims");

  const tabs = (
    <Tabs
      value={tab}
      onChange={(v) => setTab(v as MemoryDestination)}
      variant="pill"
      className="gap-0.5 rounded-lg bg-surface-soft p-0.5"
    >
      {MEMORY_TABS.map((t) => (
        <Tab
          key={t.id}
          value={t.id}
          className="rounded-md px-3 py-1 text-sm font-medium text-muted data-[active=true]:text-ink"
        >
          {t.label}
        </Tab>
      ))}
    </Tabs>
  );

  return (
    <PageModal
      open={open}
      onClose={close}
      header={{ title: "Memory", actions: tabs }}
      size="w-[min(1280px,calc(100vw-32px))] h-[min(820px,calc(100vh-32px))] sm:w-[min(1280px,calc(100vw-80px))] sm:h-[min(820px,calc(100vh-80px))]"
    >
      {/* Inset border under the title row — single delimiter, no nested glass. */}
      <div className="flex min-h-0 flex-col border-t border-line-soft">
        <MemoryPane tab={tab} onTab={setTab} />
      </div>
    </PageModal>
  );
}
