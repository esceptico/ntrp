import { useEffect, useRef, useState } from "react";
import type { AppConfig } from "../../api";
import { listScopes, type MemoryScope, type ScopeKind } from "../../api/memoryItems";
import { useStore } from "../../store";
import { TabPanels, useTabDirection } from "../ui/TabPanels";
import { DetailPlaceholder } from "./shared";
import { LensesView } from "./LensesView";
import { ClaimsView } from "./ClaimsView";
import { GraphView } from "./GraphView";

export interface MemoryScopeSel {
  kind: ScopeKind;
  key: string | null;
}

function scopeLabel(s: MemoryScope): string {
  const k = s.scope_key ? ` · ${s.scope_key.replace(/^proj_/, "")}` : "";
  const name = s.scope_kind === "user" ? "You" : s.scope_kind === "project" ? "Project" : "Session";
  return `${name}${k} (${s.count})`;
}

export type MemoryDestination = "lenses" | "claims" | "graph";
export const MEMORY_TABS: { id: MemoryDestination; label: string }[] = [
  { id: "claims", label: "Claims" },
  { id: "lenses", label: "Lenses" },
  { id: "graph", label: "Graph" },
];
const ORDER = MEMORY_TABS.map((t) => t.id);

/** Hosts the three woven destinations. Peel state threads between them: a
 *  claim peeked from a lens opens Claims focused on that claim; a provenance
 *  request opens Graph seeded on that item. */
export function MemoryPane({
  tab,
  onTab,
}: {
  tab: MemoryDestination;
  onTab: (t: MemoryDestination) => void;
}) {
  const config = useConfig();
  const [claimFocus, setClaimFocus] = useState<string | null>(null);
  const [graphFocus, setGraphFocus] = useState<string | null>(null);
  const direction = useTabDirection(ORDER, tab);

  // Memory is scoped (user / project / session). The UI used to silently query only
  // user scope, so project/session memory (most of it) was invisible. Load the scopes
  // that actually hold claims and default to the busiest one.
  const [scopes, setScopes] = useState<MemoryScope[]>([]);
  const [scope, setScope] = useState<MemoryScopeSel | null>(null);
  useEffect(() => {
    if (!config) return;
    let alive = true;
    listScopes(config)
      .then((r) => {
        if (!alive || !r.scopes.length) return;
        setScopes(r.scopes);
        setScope((cur) => cur ?? { kind: r.scopes[0].scope_kind, key: r.scopes[0].scope_key });
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [config]);

  // A peel-in (claim/provenance) carries focus to the destination; a manual tab
  // switch must NOT — else the stale focus re-applies when the unmounted view
  // remounts. Mark peel navigations so the tab-change effect leaves their focus,
  // and clear focus on any other tab change.
  const peeledRef = useRef(false);
  useEffect(() => {
    if (peeledRef.current) {
      peeledRef.current = false;
      return;
    }
    setClaimFocus(null);
    setGraphFocus(null);
  }, [tab]);

  if (!config) {
    return <DetailPlaceholder>Memory is unavailable until the app config loads.</DetailPlaceholder>;
  }

  const peekClaim = (claimId: string) => {
    setClaimFocus(claimId);
    if (tab !== "claims") peeledRef.current = true;
    onTab("claims");
  };
  const showProvenance = (itemId: string) => {
    setGraphFocus(itemId);
    if (tab !== "graph") peeledRef.current = true;
    onTab("graph");
  };

  const scopeSel = scope ?? { kind: "user" as ScopeKind, key: null };

  return (
    <div className="flex h-full min-h-0 flex-col">
      {scopes.length > 1 && (
        <div className="flex items-center gap-2 px-1 pb-2">
          <span className="text-2xs font-semibold uppercase tracking-wide text-faint">Scope</span>
          <select
            value={`${scopeSel.kind}|${scopeSel.key ?? ""}`}
            onChange={(e) => {
              const [kind, key] = e.target.value.split("|");
              setScope({ kind: kind as ScopeKind, key: key || null });
            }}
            className="rounded-md border border-line-soft bg-surface-soft/50 px-2 py-1 text-sm text-ink outline-none"
          >
            {scopes.map((s) => (
              <option key={`${s.scope_kind}|${s.scope_key ?? ""}`} value={`${s.scope_kind}|${s.scope_key ?? ""}`}>
                {scopeLabel(s)}
              </option>
            ))}
          </select>
        </div>
      )}
      <TabPanels value={tab} direction={direction} className="h-full min-h-0">
        {tab === "lenses" && (
          <LensesView config={config} scope={scopeSel} onPeekClaim={peekClaim} />
        )}
        {tab === "claims" && (
          <ClaimsView config={config} scope={scopeSel} focusId={claimFocus} onProvenance={showProvenance} />
        )}
        {tab === "graph" && <GraphView config={config} scope={scopeSel} focusId={graphFocus} />}
      </TabPanels>
    </div>
  );
}

function useConfig(): AppConfig | null {
  return useStore((s) => s.config);
}
