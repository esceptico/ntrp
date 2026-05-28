import { useStore } from "../store";
import { PageModal } from "./PageModal";
import { MemoryItemsPane } from "./memory/MemoryItemsPane";

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
      <MemoryItemsPane />
    </PageModal>
  );
}
