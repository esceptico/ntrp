import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import type { KnowledgeObject, KnowledgeObjectType, KnowledgeSourceTraceResult, KnowledgeSummary } from "../../api";
import {
  getKnowledgeObjectSourcesApi,
  getKnowledgeSummaryApi,
  listKnowledgeObjectsApi,
  synthesizeKnowledgeProfilesApi,
} from "../../api";
import { useStore } from "../../store";
import { formatRelativePast } from "../../lib/format";
import { KNOWLEDGE_LIBRARY_TYPES, knowledgeSurfaceCount } from "../../lib/knowledgeViews";
import { DetailPlaceholder, ErrorPill, GhostBtn, Pill } from "./shared";
import { ScrollBlurTop } from "../ScrollBlur";

export function KnowledgeLibraryPane() {
  const config = useStore((s) => s.config);
  const [selectedType, setSelectedType] = useState<KnowledgeObjectType>("episode");
  const [summary, setSummary] = useState<KnowledgeSummary | null>(null);
  const [items, setItems] = useState<KnowledgeObject[] | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [sources, setSources] = useState<KnowledgeSourceTraceResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [profileNames, setProfileNames] = useState("");
  const [profileLimit, setProfileLimit] = useState(20);
  const [profileEvidenceLimit, setProfileEvidenceLimit] = useState(12);
  const [generatingProfiles, setGeneratingProfiles] = useState(false);
  const [profileGenerationMessage, setProfileGenerationMessage] = useState<string | null>(null);

  const selected = useMemo(
    () => items?.find((item) => item.id === selectedId) ?? items?.[0] ?? null,
    [items, selectedId],
  );

  async function load(type = selectedType) {
    setError(null);
    setSources(null);
    try {
      const [nextSummary, nextItems] = await Promise.all([
        getKnowledgeSummaryApi(config),
        listKnowledgeObjectsApi(config, { object_type: type, limit: 100 }),
      ]);
      setSummary(nextSummary);
      setItems(nextItems.objects);
      setSelectedId(nextItems.objects[0]?.id ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function selectType(type: KnowledgeObjectType) {
    setSelectedType(type);
    setItems(null);
    await load(type);
  }

  async function generateProfiles() {
    const entityNames = profileNames
      .split(/[\n,]/)
      .map((name) => name.trim())
      .filter(Boolean);
    setGeneratingProfiles(true);
    setError(null);
    setProfileGenerationMessage(null);
    try {
      const result = await synthesizeKnowledgeProfilesApi(config, {
        apply: true,
        limit_entities: Math.max(1, Math.min(100, Math.trunc(profileLimit) || 20)),
        evidence_limit: Math.max(1, Math.min(50, Math.trunc(profileEvidenceLimit) || 12)),
        ...(entityNames.length > 0 ? { entity_names: entityNames } : {}),
      });
      setProfileGenerationMessage(`Generated/refreshed ${result.profiles.length} profile${result.profiles.length === 1 ? "" : "s"}; skipped ${result.skipped}.`);
      setSelectedType("entity_profile");
      await load("entity_profile");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setGeneratingProfiles(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    let cancelled = false;
    setSources(null);
    if (!selected) return;
    void getKnowledgeObjectSourcesApi(config, selected.id)
      .then((result) => {
        if (!cancelled) setSources(result);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [config, selected?.id]);

  return (
    <div className="grid h-full grid-cols-[250px_minmax(280px,360px)_minmax(0,1fr)]">
      <aside className="min-h-0 overflow-y-auto border-r border-line-soft px-3 py-3 scroll-thin">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h3 className="m-0 text-sm font-semibold text-ink">Library</h3>
          <GhostBtn onClick={() => void load()}>Refresh</GhostBtn>
        </div>
        {selectedType === "entity_profile" && (
          <ProfileGeneratorPanel
            names={profileNames}
            limit={profileLimit}
            evidenceLimit={profileEvidenceLimit}
            generating={generatingProfiles}
            message={profileGenerationMessage}
            onNamesChange={setProfileNames}
            onLimitChange={setProfileLimit}
            onEvidenceLimitChange={setProfileEvidenceLimit}
            onGenerate={() => void generateProfiles()}
          />
        )}
        <ul className="m-0 grid list-none gap-1 p-0">
          {KNOWLEDGE_LIBRARY_TYPES.map((view) => {
            const active = selectedType === view.type;
            const count = summary ? knowledgeSurfaceCount(summary.surfaces, view.type) : 0;
            return (
              <li key={view.type}>
                <button
                  type="button"
                  onClick={() => void selectType(view.type)}
                  className={clsx(
                    "w-full rounded-[8px] px-3 py-2 text-left transition-colors",
                    active ? "bg-surface-soft text-ink" : "text-muted hover:bg-surface-soft hover:text-ink",
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold">{view.label}</span>
                    <span className="font-mono text-xs">{count}</span>
                  </div>
                  <div className="mt-1 text-xs text-faint">{view.description}</div>
                </button>
              </li>
            );
          })}
        </ul>
      </aside>

      <section className="min-h-0 overflow-y-auto border-r border-line-soft px-3 py-3 scroll-thin">
        {error && <div className="mb-2"><ErrorPill message={error} /></div>}
        {items === null ? (
          <DetailPlaceholder>Loading</DetailPlaceholder>
        ) : items.length === 0 ? (
          <DetailPlaceholder>No objects</DetailPlaceholder>
        ) : (
          <ul className="m-0 grid list-none gap-1 p-0">
            {items.map((item) => {
              const active = selected?.id === item.id;
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(item.id)}
                    className={clsx(
                      "w-full rounded-[8px] px-3 py-2 text-left transition-colors",
                      active ? "bg-surface-soft" : "hover:bg-surface-soft",
                    )}
                  >
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Pill>{item.status}</Pill>
                      {item.scope && <Pill>{item.scope}</Pill>}
                    </div>
                    <h4 className="m-0 mt-1 line-clamp-2 text-sm font-semibold text-ink-soft">{item.title}</h4>
                    <p className="m-0 mt-1 line-clamp-2 text-xs leading-snug text-faint">{item.text}</p>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className="min-h-0 overflow-y-auto px-7 py-5 scroll-thin">
        <ScrollBlurTop />
        {!selected ? (
          <DetailPlaceholder>Select an object</DetailPlaceholder>
        ) : (
          <div className="grid gap-5">
            <div>
              <div className="mb-2 flex flex-wrap items-center gap-1.5">
                <Pill>{selected.object_type}</Pill>
                <Pill>{selected.status}</Pill>
                <Pill>{selected.activation}</Pill>
                <Pill>{selected.proactiveness_level}</Pill>
                <span className="text-xs text-faint">updated {formatRelativePast(selected.updated_at)}</span>
              </div>
              <h3 className="m-0 text-xl font-semibold text-ink">{selected.title}</h3>
              <p className="m-0 mt-3 whitespace-pre-wrap text-sm leading-relaxed text-ink-soft">{selected.text}</p>
            </div>

            <div className="flex flex-wrap gap-2">
              <Pill>score {selected.score.toFixed(2)}</Pill>
              <Pill>sources {selected.source_ids.length}</Pill>
              {selected.reviewed_at && <Pill>reviewed {formatRelativePast(selected.reviewed_at)}</Pill>}
            </div>

            <section className="rounded-[8px] border border-line-soft bg-bg-main/50 px-3 py-3">
              <h4 className="m-0 mb-2 text-2xs font-semibold uppercase tracking-[0.08em] text-faint">Sources</h4>
              {!sources ? (
                <p className="m-0 text-sm italic text-faint">Loading sources</p>
              ) : sources.sources.length === 0 ? (
                <p className="m-0 text-sm italic text-faint">No source trace</p>
              ) : (
                <ul className="m-0 grid list-none gap-2 p-0">
                  {sources.sources.map((source) => (
                    <li key={source.source_id} className="rounded-[7px] border border-line-soft bg-surface-soft/50 px-3 py-2">
                      <div className="mb-1 flex flex-wrap items-center gap-1.5">
                        <Pill>{sourceKind(source.source_id)}</Pill>
                        <span className="font-mono text-2xs text-faint">{source.source_id}</span>
                      </div>
                      {source.object ? (
                        <div>
                          <div className="text-sm font-semibold text-ink-soft">{source.object.title}</div>
                          <div className="mt-1 line-clamp-3 whitespace-pre-wrap text-xs leading-snug text-faint">{source.object.text}</div>
                        </div>
                      ) : (
                        <div className="text-xs text-faint">External/source-native reference; no local object yet.</div>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section>
              <h4 className="m-0 mb-2 text-2xs font-semibold uppercase tracking-[0.08em] text-faint">Details</h4>
              <MetadataRows metadata={selected.metadata} />
            </section>
          </div>
        )}
      </section>
    </div>
  );
}

function ProfileGeneratorPanel({
  names,
  limit,
  evidenceLimit,
  generating,
  message,
  onNamesChange,
  onLimitChange,
  onEvidenceLimitChange,
  onGenerate,
}: {
  names: string;
  limit: number;
  evidenceLimit: number;
  generating: boolean;
  message: string | null;
  onNamesChange: (value: string) => void;
  onLimitChange: (value: number) => void;
  onEvidenceLimitChange: (value: number) => void;
  onGenerate: () => void;
}) {
  return (
    <section className="mb-3 rounded-[8px] border border-line-soft bg-bg-main/50 px-3 py-3">
      <div className="text-sm font-semibold text-ink-soft">Generate/Refresh profiles</div>
      <p className="m-0 mt-1 text-xs leading-snug text-faint">
        Refreshes source-backed profiles from current facts/patterns. Leave names empty for auto candidates.
      </p>
      <textarea
        value={names}
        onChange={(e) => onNamesChange(e.target.value)}
        rows={3}
        placeholder="Dex, Regina Lin"
        className="mt-2 w-full resize-none rounded-[7px] border border-line-soft bg-bg-main px-2 py-1.5 text-xs text-ink outline-none placeholder:text-faint focus:border-accent/60"
      />
      <div className="mt-2 grid grid-cols-2 gap-2">
        <label className="grid gap-1 text-2xs font-semibold uppercase tracking-[0.08em] text-faint">
          Limit
          <input
            type="number"
            min={1}
            max={100}
            value={limit}
            onChange={(e) => onLimitChange(Number(e.target.value))}
            className="rounded-[7px] border border-line-soft bg-bg-main px-2 py-1.5 font-mono text-xs normal-case tracking-normal text-ink outline-none focus:border-accent/60"
          />
        </label>
        <label className="grid gap-1 text-2xs font-semibold uppercase tracking-[0.08em] text-faint">
          Evidence
          <input
            type="number"
            min={1}
            max={50}
            value={evidenceLimit}
            onChange={(e) => onEvidenceLimitChange(Number(e.target.value))}
            className="rounded-[7px] border border-line-soft bg-bg-main px-2 py-1.5 font-mono text-xs normal-case tracking-normal text-ink outline-none focus:border-accent/60"
          />
        </label>
      </div>
      <button
        type="button"
        disabled={generating}
        onClick={onGenerate}
        className={clsx(
          "mt-2 w-full rounded-[7px] border border-line-soft px-3 py-1.5 text-sm font-semibold transition-colors",
          generating ? "cursor-not-allowed text-faint" : "bg-surface-soft text-ink-soft hover:bg-bg-main",
        )}
      >
        {generating ? "Refreshing" : "Generate/Refresh now"}
      </button>
      {message && <p className="m-0 mt-2 text-xs leading-snug text-muted">{message}</p>}
    </section>
  );
}

function sourceKind(sourceId: string): string {
  const prefix = sourceId.includes(":") ? sourceId.split(":", 1)[0] : "source";
  if (prefix === "knowledge") return "memory";
  return prefix;
}

function MetadataRows({ metadata }: { metadata: Record<string, unknown> }) {
  const rows = Object.entries(metadata)
    .filter(([key]) => key !== "entity_graph" && key !== "entities")
    .map(([key, value]) => [key, formatMetadataValue(value)] as const)
    .filter(([, value]) => value.length > 0);

  if (rows.length === 0) {
    return <p className="m-0 text-sm italic text-faint">No extra details</p>;
  }

  return (
    <dl className="m-0 grid gap-2">
      {rows.map(([key, value]) => (
        <div key={key} className="grid grid-cols-[160px_minmax(0,1fr)] gap-3 rounded-[7px] border border-line-soft px-3 py-2">
          <dt className="font-mono text-2xs text-faint">{humanizeKey(key)}</dt>
          <dd className="m-0 whitespace-pre-wrap break-words text-sm text-ink-soft">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function humanizeKey(key: string): string {
  return key.replaceAll("_", " ");
}

function formatMetadataValue(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map(formatMetadataValue).filter(Boolean).join(", ");
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, nested]) => `${humanizeKey(key)}: ${formatMetadataValue(nested)}`)
      .filter((line) => !line.endsWith(": "))
      .join("\n");
  }
  return String(value);
}
