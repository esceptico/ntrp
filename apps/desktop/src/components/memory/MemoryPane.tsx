import { useEffect, useRef, useState } from "react";
import clsx from "clsx";
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

  // Memory is ONE connected store. The default view is everything (scope = null);
  // scope is an optional FILTER, not a wall. (Scope isolation governs what the agent
  // recalls, not what the human browses.) Load the scopes only to offer filter chips.
  const [scopes, setScopes] = useState<MemoryScope[]>([]);
  const [scope, setScope] = useState<MemoryScopeSel | null>(null); // null = All
  useEffect(() => {
    if (!config) return;
    let alive = true;
    listScopes(config)
      .then((r) => {
        if (alive) setScopes(r.scopes);
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

  const isActive = (s: MemoryScope | null) =>
    s === null ? scope === null : scope?.kind === s.scope_kind && scope?.key === s.scope_key;

  return (
    <div className="flex h-full min-h-0 flex-col">
      {scopes.length > 1 && (
        <div className="flex flex-wrap items-center gap-1 px-1 pb-2">
          <ScopeChip label="All" active={isActive(null)} onClick={() => setScope(null)} />
          {scopes.map((s) => (
            <ScopeChip
              key={`${s.scope_kind}|${s.scope_key ?? ""}`}
              label={scopeLabel(s)}
              active={isActive(s)}
              onClick={() => setScope({ kind: s.scope_kind, key: s.scope_key })}
            />
          ))}
        </div>
      )}
      <TabPanels value={tab} direction={direction} className="h-full min-h-0">
        {tab === "lenses" && (
          <LensesView config={config} scope={scope} onPeekClaim={peekClaim} />
        )}
        {tab === "claims" && (
          <ClaimsView config={config} scope={scope} focusId={claimFocus} onProvenance={showProvenance} />
        )}
        {tab === "graph" && <GraphView config={config} scope={scope} focusId={graphFocus} />}
      </TabPanels>
    </div>
  );
}

function useConfig(): AppConfig | null {
  return useStore((s) => s.config);
}

/** Scope filter chip — the app's pill language (matches the composer effort pills). */
function ScopeChip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        "h-6 px-2.5 rounded-full text-xs font-medium tracking-[-0.005em] transition-colors select-none",
        active ? "bg-accent-soft text-accent-strong" : "text-muted hover:bg-surface-soft hover:text-ink",
      )}
    >
      {label}
    </button>
  );
}
