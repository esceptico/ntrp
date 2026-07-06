import { useEffect } from "react";
import { useStore } from "@/stores";
import { fetchSlicesOverview } from "@/actions/slices";

/** Fetches the slices overview whenever the server connection comes up.
 *  Keyed on `connected`, not mount: on a fresh boot the mount fires before
 *  the handshake, the fetch fails silently, and Home would show a permanent
 *  false "All clear." Connect-keying also covers server restarts. Live
 *  refetches on `slices_changed`/`automation_finished` are handled by
 *  `useAutomationEvents` (the hook that owns the automation SSE stream). */
export function useSlicesData() {
  const overview = useStore((s) => s.slices.overview);
  const loading = useStore((s) => s.slices.loading);
  const connected = useStore((s) => s.connected);

  useEffect(() => {
    if (connected) void fetchSlicesOverview();
  }, [connected]);

  return { overview, loading };
}
