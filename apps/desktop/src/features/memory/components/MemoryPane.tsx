import type { AppConfig } from "@/api";
import { useStore } from "@/stores";
import { DetailPlaceholder } from "@/features/memory/components/shared";
import { ArtifactMemoryView } from "@/features/memory/components/ArtifactMemoryView";

/** Hosts the directory-first artifact-backed memory browser. */
export function MemoryPane() {
  const config = useConfig();

  if (!config) {
    return <DetailPlaceholder>Memory is unavailable until the app config loads.</DetailPlaceholder>;
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ArtifactMemoryView config={config} />
    </div>
  );
}

function useConfig(): AppConfig | null {
  return useStore((s) => s.config);
}
