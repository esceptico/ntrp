import { Skeleton } from "@/components/ui/Skeleton";

/** Loading placeholder for settings tabs — a section label + a few rows, so a
 *  tab renders a designed skeleton (matching ContextTab/ArchiveTab) instead of
 *  flashing a bare "Loading…" string. `role="status"` + `label` preserves the
 *  screen-reader announcement the plain text used to provide. */
export function SettingsTabSkeleton({
  rows = 4,
  label = "Loading…",
  variant = "rows",
}: {
  rows?: number;
  label?: string;
  /** rows = a section label + list rows (Models/Tools/Agent); cards = taller
   *  blocks matching the provider/service card tabs. */
  variant?: "rows" | "cards";
}) {
  const cards = variant === "cards";
  return (
    <div className="grid gap-3" role="status" aria-label={label}>
      {!cards && <Skeleton width="40%" height={14} />}
      {Array.from({ length: cards ? 3 : rows }).map((_, i) => (
        <Skeleton key={i} height={cards ? 72 : 44} radius={cards ? 12 : 10} />
      ))}
    </div>
  );
}
