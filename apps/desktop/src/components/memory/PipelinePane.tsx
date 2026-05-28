import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { AlertTriangle, RefreshCw, Sparkles, Wand2 } from "lucide-react";
import clsx from "clsx";
import { useStore } from "../../store";
import {
  approveMemoryProposalApi,
  listMemoryProposalsApi,
  rejectMemoryProposalApi,
  runMemoryPatternFinderApi,
  runMemorySkillInducerApi,
  scanMemoryContradictionsApi,
  type ContradictionScanResult,
  type MemoryProposal,
  type MemoryProposalStatus,
  type PatternFinderPass1Result,
  type PatternFinderPass2Result,
  type SkillInducerResult,
} from "../../api";
import { ICON } from "../../lib/icons";
import {
  DangerBtn,
  DetailMeta,
  DetailPlaceholder,
  DetailShell,
  ErrorPill,
  GhostBtn,
  ListColumn,
  ListError,
  MetaGrid,
  PaneShell,
  Pill,
  PrimaryBtn,
  Sep,
} from "./shared";

// ─── Sub-tabs ─────────────────────────────────────────────────────────

type PipelineSubTab = "proposals" | "contradictions";

const SUB_TABS: { id: PipelineSubTab; label: string }[] = [
  { id: "proposals", label: "Proposals" },
  { id: "contradictions", label: "Contradictions" },
];

const STATUS_FILTERS: { id: MemoryProposalStatus; label: string }[] = [
  { id: "open", label: "Open" },
  { id: "approved", label: "Approved" },
  { id: "rejected", label: "Rejected" },
];

// ─── Top-level pane ───────────────────────────────────────────────────

export function PipelinePane() {
  const [tab, setTab] = useState<PipelineSubTab>("proposals");
  const [runMessage, setRunMessage] = useState<RunMessage | null>(null);

  return (
    <div className="flex flex-col h-full min-h-0">
      <RunBar onResult={setRunMessage} message={runMessage} onDismiss={() => setRunMessage(null)} />

      <div className="px-6 pt-2 pb-3 flex items-center gap-4 border-b border-line-soft">
        {SUB_TABS.map((t) => (
          <SubTabButton key={t.id} label={t.label} active={tab === t.id} onClick={() => setTab(t.id)} />
        ))}
      </div>

      <div className="flex-1 min-h-0">
        {tab === "proposals" ? <ProposalsPane /> : <ContradictionsPane />}
      </div>
    </div>
  );
}

function SubTabButton({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        "relative pb-2 -mb-px text-sm font-medium tracking-[-0.005em] transition-colors",
        active ? "text-ink" : "text-muted hover:text-ink",
      )}
    >
      {label}
      {active && <span className="absolute left-0 right-0 bottom-0 h-[2px] rounded-full bg-ink" />}
    </button>
  );
}

// ─── Run bar (manual triggers) ────────────────────────────────────────

interface RunMessage {
  tone: "ok" | "warn" | "bad";
  text: string;
}

function RunBar({
  onResult,
  message,
  onDismiss,
}: {
  onResult: (msg: RunMessage) => void;
  message: RunMessage | null;
  onDismiss: () => void;
}) {
  const config = useStore((s) => s.config);
  const [busy, setBusy] = useState<null | "pf1" | "pf2" | "pfboth" | "inducer" | "scan">(null);

  async function run<T>(key: typeof busy, label: string, fn: () => Promise<T>, formatOk: (result: T) => string) {
    if (busy) return;
    setBusy(key);
    onDismiss();
    try {
      const result = await fn();
      onResult({ tone: "ok", text: `${label}: ${formatOk(result)}` });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      onResult({ tone: "bad", text: `${label} failed: ${msg}` });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="px-6 pt-5 pb-4 flex flex-wrap items-center gap-2">
      <span className="text-xs font-medium uppercase tracking-wider text-faint mr-1">Run</span>

      <RunButton
        icon={<RefreshCw size={ICON.SM} strokeWidth={1.8} />}
        label="Pattern finder · pass 1"
        busy={busy === "pf1"}
        disabled={busy !== null}
        onClick={() =>
          run("pf1", "Pattern finder pass 1", () => runMemoryPatternFinderApi(config, { pass: 1 }), (r) => formatPass1(r as PatternFinderPass1Result))
        }
      />
      <RunButton
        icon={<RefreshCw size={ICON.SM} strokeWidth={1.8} />}
        label="Pattern finder · pass 2"
        busy={busy === "pf2"}
        disabled={busy !== null}
        onClick={() =>
          run("pf2", "Pattern finder pass 2", () => runMemoryPatternFinderApi(config, { pass: 2 }), (r) => {
            const payload = (r as { pass2: PatternFinderPass2Result }).pass2;
            return formatPass2(payload);
          })
        }
      />
      <RunButton
        icon={<Wand2 size={ICON.SM} strokeWidth={1.8} />}
        label="Skill inducer"
        busy={busy === "inducer"}
        disabled={busy !== null}
        onClick={() =>
          run("inducer", "Skill inducer", () => runMemorySkillInducerApi(config), (r) => formatInducer(r as SkillInducerResult))
        }
      />
      <RunButton
        icon={<AlertTriangle size={ICON.SM} strokeWidth={1.8} />}
        label="Contradiction scan"
        busy={busy === "scan"}
        disabled={busy !== null}
        onClick={() =>
          run("scan", "Contradiction scan", () => scanMemoryContradictionsApi(config), (r) =>
            formatScan(r as ContradictionScanResult),
          )
        }
      />

      {message && (
        <div className="ml-auto flex items-center gap-2 min-w-0">
          <ResultPill tone={message.tone}>{message.text}</ResultPill>
          <GhostBtn onClick={onDismiss} aria-label="Dismiss">
            ×
          </GhostBtn>
        </div>
      )}
    </div>
  );
}

function RunButton({
  icon,
  label,
  onClick,
  busy,
  disabled,
}: {
  icon: ReactNode;
  label: string;
  onClick: () => void;
  busy: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={clsx(
        "inline-flex items-center gap-1.5 h-7 px-2.5 rounded-md border text-sm transition-colors",
        "border-line-soft bg-surface-soft text-ink-soft hover:text-ink hover:border-line",
        "disabled:opacity-50 disabled:cursor-not-allowed",
        busy && "animate-pulse",
      )}
    >
      <span className={clsx("inline-flex", busy && "animate-spin")}>{busy ? <RefreshCw size={ICON.SM} strokeWidth={1.8} /> : icon}</span>
      {label}
    </button>
  );
}

function ResultPill({ children, tone }: { children: ReactNode; tone: "ok" | "warn" | "bad" }) {
  return <Pill tone={tone}>{children}</Pill>;
}

// ─── Proposals ────────────────────────────────────────────────────────

function ProposalsPane() {
  const config = useStore((s) => s.config);
  const [status, setStatus] = useState<MemoryProposalStatus>("open");
  const [proposals, setProposals] = useState<MemoryProposal[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { proposals: list } = await listMemoryProposalsApi(config, { status });
      setProposals(list);
      setSelectedId((current) => (current && list.some((p) => p.id === current) ? current : list[0]?.id ?? null));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setProposals([]);
    } finally {
      setLoading(false);
    }
  }, [config, status]);

  useEffect(() => {
    void load();
  }, [load, reloadKey]);

  const selected = useMemo(() => proposals.find((p) => p.id === selectedId) ?? null, [proposals, selectedId]);

  async function handleApprove() {
    if (!selected || actionBusy) return;
    setActionBusy(true);
    setActionError(null);
    try {
      await approveMemoryProposalApi(config, selected.id);
      setReloadKey((k) => k + 1);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setActionBusy(false);
    }
  }

  async function handleReject() {
    if (!selected || actionBusy) return;
    setActionBusy(true);
    setActionError(null);
    try {
      await rejectMemoryProposalApi(config, selected.id);
      setReloadKey((k) => k + 1);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setActionBusy(false);
    }
  }

  return (
    <PaneShell
      list={
        <ListColumn
          toolbar={
            <div className="flex items-center gap-1.5 flex-wrap">
              {STATUS_FILTERS.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => setStatus(f.id)}
                  className={clsx(
                    "inline-flex items-center h-6 px-2 rounded-md text-xs font-medium transition-colors",
                    status === f.id
                      ? "bg-ink text-on-ink"
                      : "text-muted hover:text-ink hover:bg-surface-soft",
                  )}
                >
                  {f.label}
                </button>
              ))}
              <button
                type="button"
                onClick={() => setReloadKey((k) => k + 1)}
                aria-label="Reload"
                className="ml-auto inline-flex items-center justify-center w-6 h-6 rounded-md text-muted hover:text-ink hover:bg-surface-soft transition-colors"
              >
                <RefreshCw size={ICON.XS} strokeWidth={1.8} />
              </button>
            </div>
          }
          items={proposals}
          loading={loading}
          error={error ? <ListError title="Failed to load proposals" message={error} /> : undefined}
          empty={`No ${status} proposals.`}
          totalLabel={proposals.length ? `${proposals.length} ${status}` : null}
          renderItem={(proposal) => (
            <ProposalRow
              key={proposal.id}
              proposal={proposal}
              active={proposal.id === selectedId}
              onSelect={() => setSelectedId(proposal.id)}
            />
          )}
        />
      }
      detail={
        selected ? (
          <DetailShell
            header={
              <ProposalHeader proposal={selected} />
            }
            body={<ProposalBody proposal={selected} />}
            meta={<ProposalMeta proposal={selected} />}
            actions={
              <>
                {actionError && <ErrorPill message={actionError} />}
                <DangerBtn onClick={handleReject} disabled={actionBusy || selected.status !== "open"}>
                  Reject
                </DangerBtn>
                <PrimaryBtn onClick={handleApprove} disabled={actionBusy || selected.status !== "open"}>
                  {actionBusy ? "Working…" : "Approve"}
                </PrimaryBtn>
              </>
            }
          />
        ) : (
          <DetailPlaceholder>
            {loading ? "Loading…" : "Select a proposal."}
          </DetailPlaceholder>
        )
      }
    />
  );
}

function ProposalRow({
  proposal,
  active,
  onSelect,
}: {
  proposal: MemoryProposal;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        className={clsx(
          "w-full text-left px-3 py-2 rounded-[8px] transition-colors",
          active ? "bg-surface-soft" : "hover:bg-surface-soft/60",
        )}
      >
        <div className="flex items-center gap-2 min-w-0">
          <Sparkles size={ICON.XS} strokeWidth={1.8} className="shrink-0 text-muted" />
          <span className="text-sm font-medium text-ink truncate">{proposal.slug || "(no slug)"}</span>
        </div>
        <div className="mt-1 ml-[19px] flex items-center gap-1.5 text-xs text-faint">
          <StatusPill status={proposal.status} />
          <Sep />
          <span>{proposal.source_claim_count} {proposal.source_claim_count === 1 ? "claim" : "claims"}</span>
          <Sep />
          <span className="truncate">{proposal.scope}</span>
        </div>
      </button>
    </li>
  );
}

function ProposalHeader({ proposal }: { proposal: MemoryProposal }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0">
        <div className="flex items-center gap-2 text-xs text-faint">
          <span>proposal</span>
          <Sep />
          <StatusPill status={proposal.status} />
          <Sep />
          <span className="font-mono text-[11px] truncate">{proposal.id}</span>
        </div>
        <h3 className="m-0 mt-1 text-lg font-semibold tracking-[-0.01em] text-ink truncate">
          {proposal.slug || "(unnamed)"}
        </h3>
      </div>
    </div>
  );
}

function ProposalBody({ proposal }: { proposal: MemoryProposal }) {
  return (
    <pre className="m-0 mt-2 max-h-[460px] overflow-auto scroll-thin rounded-[8px] border border-line-soft bg-code-bg px-4 py-3 text-[13px] leading-relaxed text-ink-soft whitespace-pre-wrap font-mono">
      {proposal.content}
    </pre>
  );
}

function ProposalMeta({ proposal }: { proposal: MemoryProposal }) {
  return (
    <MetaGrid
      rows={[
        { label: "Slug", value: proposal.slug || "—" },
        { label: "Status", value: proposal.status },
        { label: "Sources", value: `${proposal.source_claim_count} claim${proposal.source_claim_count === 1 ? "" : "s"}` },
        { label: "Scope", value: proposal.scope },
        { label: "Draft path", value: proposal.draft_path || "—", mono: true },
        { label: "Proposal id", value: proposal.id, mono: true },
      ]}
    />
  );
}

function StatusPill({ status }: { status: MemoryProposalStatus }) {
  const tone = status === "open" ? "accent" : status === "approved" ? "ok" : "warn";
  return <Pill tone={tone}>{status}</Pill>;
}

// ─── Contradictions (v1: scan + show last result) ─────────────────────

function ContradictionsPane() {
  const config = useStore((s) => s.config);
  const [result, setResult] = useState<ContradictionScanResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runScan() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const r = await scanMemoryContradictionsApi(config);
      setResult(r);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid h-full place-items-center px-8">
      <div className="max-w-[520px] w-full text-center">
        <div className="grid place-items-center w-12 h-12 mx-auto mb-4 rounded-[12px] bg-surface-soft text-muted">
          <AlertTriangle size={ICON.XL} strokeWidth={1.6} />
        </div>
        <h3 className="m-0 text-base font-semibold tracking-[-0.005em] text-ink">Contradiction watcher</h3>
        <p className="mt-2 mb-5 text-sm leading-[1.55] text-muted">
          Runs alongside pattern-finder pass&nbsp;2 automatically. Trigger a manual scan to look for new conflicting claims in the recent window.
        </p>

        <div className="flex items-center justify-center gap-2">
          <PrimaryBtn onClick={runScan} disabled={busy}>
            {busy ? "Scanning…" : "Run scan"}
          </PrimaryBtn>
        </div>

        {error && (
          <div className="mt-5">
            <ListError title="Scan failed" message={error} />
          </div>
        )}

        {result && !error && (
          <div className="mt-6 rounded-[10px] border border-line-soft bg-bg-main/60 px-4 py-3 text-left">
            <DetailMeta>
              <span>scope: <span className="text-ink-soft">{result.scope}</span></span>
              <Sep />
              <span>window: <span className="text-ink-soft">{result.window_days}d</span></span>
            </DetailMeta>
            <div className="mt-3 grid grid-cols-2 gap-3">
              <Stat label="Claims scanned" value={result.claims_scanned} />
              <Stat label="Contradictions" value={result.contradictions_found} accent={result.contradictions_found > 0} />
            </div>
          </div>
        )}

        {!result && !error && !busy && (
          <p className="mt-5 text-xs text-faint">No scan yet. Results appear here.</p>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: number; accent?: boolean }) {
  return (
    <div className="rounded-[8px] bg-surface-soft px-3 py-2.5">
      <div className="text-xs text-faint">{label}</div>
      <div className={clsx("mt-0.5 text-xl font-semibold tabular-nums tracking-[-0.01em]", accent ? "text-accent-strong" : "text-ink")}>
        {value}
      </div>
    </div>
  );
}

// ─── Formatters ───────────────────────────────────────────────────────

function formatPass1(r: PatternFinderPass1Result) {
  return `${r.observations_written} written, ${r.clusters_found} clusters · ${r.elapsed_ms}ms`;
}

function formatPass2(r: PatternFinderPass2Result) {
  return `${r.claims_written} claims, ${r.claims_superseded} superseded · ${r.elapsed_ms}ms`;
}

function formatInducer(r: SkillInducerResult) {
  return `${r.proposals_written} proposals · ${r.toolable_claims}/${r.claims_considered} toolable · ${r.elapsed_ms}ms`;
}

function formatScan(r: ContradictionScanResult) {
  return `${r.contradictions_found} contradictions · ${r.claims_scanned} scanned`;
}
