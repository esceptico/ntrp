import { useEffect } from "react";
import { useStore } from "@/stores";
import { fetchSlicesOverview } from "@/actions/slices";

/** Fetches the slices overview on mount. Live refetches on `slices_changed`/
 *  `automation_finished` are handled by `useAutomationEvents` (the hook that
 *  already owns the automation SSE stream) — this hook only owns the
 *  initial load and exposes the current overview/loading state. */
export function useSlicesData() {
  const overview = useStore((s) => s.slices.overview);
  const loading = useStore((s) => s.slices.loading);

  useEffect(() => {
    void fetchSlicesOverview();
  }, []);

  return { overview, loading };
}
