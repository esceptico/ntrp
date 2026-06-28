import { useStore } from "@/stores";
import { MemoryPane } from "@/features/memory/components/MemoryPane";
import { PageModal } from "@/components/ui/PageModal";

/** Directory-first generated memory artifact browser. */
export function MemoryModal() {
  const open = useStore((s) => s.memoryOpen);
  const close = useStore((s) => s.closeMemory);

  return (
    <PageModal
      open={open}
      onClose={close}
      header={{ title: "Memory" }}
      size="w-[min(1280px,calc(100vw-32px))] h-[min(820px,calc(100vh-32px))] sm:w-[min(1280px,calc(100vw-80px))] sm:h-[min(820px,calc(100vh-80px))]"
    >
      {/* Inset border under the title row — single delimiter. */}
      <div className="flex min-h-0 flex-col border-t border-line-soft">
        <MemoryPane />
      </div>
    </PageModal>
  );
}
