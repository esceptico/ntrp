import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import clsx from "clsx";
import {
  CalendarDays,
  CheckCircle2,
  KeyRound,
  Loader2,
  Mail,
  MessageCircle,
  RefreshCw,
  Trash2,
} from "lucide-react";
import {
  addGmailAccountApi,
  connectServiceApi,
  disconnectServiceApi,
  listGmailAccountsApi,
  listServicesApi,
  removeGmailAccountApi,
  type GmailAccount,
  type ServiceConnection,
} from "../../api";
import { fetchServerConfig, updateServerConfig } from "../../actions";
import { useStore } from "../../store";
import {
  googleConnectionSummary,
  type GoogleConnectionSummary,
  serviceActionLabel,
  serviceConnectionPill,
} from "../../lib/integrationConnection";
import {
  settingsErrorMessage,
  settingsErrorTitle,
  shouldShowLoadedSettingsContent,
} from "../../lib/settingsLoadState";
import { SettingsConnectionHint, SettingsInlineError } from "./SettingsNotice";

export function IntegrationsTab() {
  const config = useStore((s) => s.config);
  const serverConfig = useStore((s) => s.serverConfig);
  const [services, setServices] = useState<ServiceConnection[]>([]);
  const [gmailAccounts, setGmailAccounts] = useState<GmailAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loadedOnce, setLoadedOnce] = useState(false);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [serviceKey, setServiceKey] = useState("");

  const googleEnabled = serverConfig?.google_enabled ?? false;
  const slackServices = useMemo(
    () => services.filter((service) => service.id.startsWith("slack_")),
    [services],
  );
  const connectedSlackServices = useMemo(
    () => slackServices.filter((service) => service.connected),
    [slackServices],
  );
  const setupSlackServices = useMemo(
    () => slackServices.filter((service) => !service.connected),
    [slackServices],
  );
  const googleSummary = useMemo(
    () => googleConnectionSummary(googleEnabled, gmailAccounts),
    [gmailAccounts, googleEnabled],
  );

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextServices, nextGmail] = await Promise.all([
        listServicesApi(config),
        listGmailAccountsApi(config),
      ]);
      setServices(nextServices);
      setGmailAccounts(nextGmail);
      setLoadedOnce(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [config]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function toggleGoogle(enabled: boolean) {
    setPendingId("google");
    setError(null);
    try {
      await updateServerConfig({ integrations: { google: enabled } });
      await fetchServerConfig();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPendingId(null);
    }
  }

  async function addGoogleAccount() {
    setPendingId("gmail:add");
    setError(null);
    try {
      await addGmailAccountApi(config);
      if (!googleEnabled) {
        await updateServerConfig({ integrations: { google: true } });
      }
      await fetchServerConfig();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPendingId(null);
    }
  }

  async function removeGoogleAccount(account: GmailAccount) {
    setPendingId(`gmail:${account.token_file}`);
    setError(null);
    try {
      await removeGmailAccountApi(config, account.token_file);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPendingId(null);
    }
  }

  async function connectService(service: ServiceConnection) {
    if (!serviceKey.trim()) return;
    setPendingId(service.id);
    setError(null);
    try {
      await connectServiceApi(config, service.id, serviceKey.trim());
      setEditingId(null);
      setServiceKey("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPendingId(null);
    }
  }

  async function disconnectService(service: ServiceConnection) {
    setPendingId(service.id);
    setError(null);
    try {
      await disconnectServiceApi(config, service.id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPendingId(null);
    }
  }

  const hasLoadedData = loadedOnce || services.length > 0 || gmailAccounts.length > 0;
  const showContent = shouldShowLoadedSettingsContent({ loading, error, hasData: hasLoadedData });

  return (
    <div className="grid gap-5">
      <div className="flex items-start justify-between gap-3">
        <p className="m-0 text-[13px] text-muted leading-[1.45] max-w-[540px]">
          Connect the data and action providers ntrp can use as tools. Model providers stay in
          Providers; MCP servers stay in MCP.
        </p>
        <button
          type="button"
          onClick={() => void refresh()}
          disabled={loading}
          className="inline-flex items-center gap-1.5 h-8 px-2.5 rounded-md border border-line bg-surface text-[12.5px] text-ink-soft hover:border-line-strong transition-colors disabled:opacity-50"
        >
          <RefreshCw size={13} strokeWidth={1.8} className={clsx(loading && "animate-spin")} />
          Refresh
        </button>
      </div>

      {error && (
        <SettingsInlineError
          title={settingsErrorTitle("integrations", hasLoadedData)}
          message={settingsErrorMessage(error)}
        />
      )}

      {loading && !hasLoadedData ? (
        <div className="text-[13px] text-faint">Loading integrations…</div>
      ) : !showContent ? (
        <SettingsConnectionHint />
      ) : (
        <>
          <IntegrationsReadinessCard
            google={googleSummary}
            connectedSlackCount={connectedSlackServices.length}
          />

          <GoogleCard
            enabled={googleEnabled}
            summary={googleSummary}
            accounts={gmailAccounts}
            pendingId={pendingId}
            onToggle={toggleGoogle}
            onAdd={addGoogleAccount}
            onRemove={removeGoogleAccount}
          />

          <ServiceCard
            connectedServices={connectedSlackServices}
            setupServices={setupSlackServices}
            editingId={editingId}
            serviceKey={serviceKey}
            pendingId={pendingId}
            onEdit={(service) => {
              setEditingId(service.id);
              setServiceKey("");
            }}
            onCancel={() => {
              setEditingId(null);
              setServiceKey("");
            }}
            onKeyChange={setServiceKey}
            onConnect={connectService}
            onDisconnect={disconnectService}
          />
        </>
      )}
    </div>
  );
}

function IntegrationsReadinessCard({
  google,
  connectedSlackCount,
}: {
  google: GoogleConnectionSummary;
  connectedSlackCount: number;
}) {
  const readyCount = (google.tone === "ready" ? 1 : 0) + connectedSlackCount;
  return (
    <section className="rounded-[12px] border border-line-soft bg-surface-soft/45 px-3.5 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={clsx(
            "inline-flex items-center rounded-full px-2 py-0.5 text-[11.5px] font-medium",
            readyCount > 0 ? "bg-ok-soft text-ok" : "bg-warn-soft text-warn",
          )}
        >
          {readyCount > 0 ? "Tools ready" : "Connect tools"}
        </span>
        <div className="text-[13px] text-ink-soft">
          Google: {google.label} · Slack: {connectedSlackCount || "none"}
        </div>
      </div>
      <div className="mt-1.5 text-[12px] text-faint">
        Tool integrations are optional, but connected tools become available to the agent.
      </div>
    </section>
  );
}

function GoogleCard({
  enabled,
  summary,
  accounts,
  pendingId,
  onToggle,
  onAdd,
  onRemove,
}: {
  enabled: boolean;
  summary: GoogleConnectionSummary;
  accounts: GmailAccount[];
  pendingId: string | null;
  onToggle: (enabled: boolean) => Promise<void>;
  onAdd: () => Promise<void>;
  onRemove: (account: GmailAccount) => Promise<void>;
}) {
  const pendingGoogle = pendingId === "google";
  const pendingAdd = pendingId === "gmail:add";
  const summaryTone = {
    ready: "bg-ok-soft text-ok",
    paused: "bg-warn-soft text-warn",
    setup: "bg-surface-soft text-muted",
  }[summary.tone];

  return (
    <section className="rounded-[12px] border border-line-soft bg-surface overflow-hidden">
      <div className="flex flex-wrap items-start gap-3 px-3.5 py-3">
        <div className="min-w-[150px] flex-1 grid gap-1">
          <div className="flex items-center gap-2 min-w-0">
            <GoogleIcon enabled={enabled} />
            <div className="text-[13.5px] font-medium text-ink truncate">Google Workspace</div>
            <span className={clsx("shrink-0 px-1.5 py-0.5 rounded-full text-[11px] font-medium", summaryTone)}>
              {summary.label}
            </span>
          </div>
          <div className="text-[12px] text-faint leading-[1.4]">
            Gmail and Calendar share the same Google account token.
          </div>
          <div className="text-[12px] text-muted font-mono truncate">
            {summary.detail}
          </div>
        </div>

        <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
          <button
            type="button"
            onClick={() => void onAdd()}
            disabled={pendingAdd}
            className="h-8 px-2.5 rounded-md border border-line bg-surface text-[12.5px] text-ink-soft hover:border-line-strong transition-colors disabled:opacity-50"
          >
            {pendingAdd ? "Connecting…" : "Add account"}
          </button>
          <button
            type="button"
            onClick={() => void onToggle(!enabled)}
            disabled={pendingGoogle}
            className={clsx(
              "h-8 px-3 rounded-md text-[12.5px] font-medium transition-colors disabled:opacity-50",
              enabled
                ? "border border-line bg-surface text-ink-soft hover:border-line-strong"
                : "bg-ink text-on-ink hover:opacity-90",
            )}
          >
            {pendingGoogle ? "Saving…" : enabled ? "Disable" : "Enable"}
          </button>
        </div>
      </div>

      {accounts.length > 0 && (
        <div className="grid gap-1 px-3.5 py-2.5 bg-surface-soft/35">
          {accounts.map((account) => (
            <div
              key={account.token_file}
              className="grid grid-cols-[minmax(0,1fr)_auto] gap-2 items-center text-[12.5px]"
            >
              <div className="min-w-0">
                <div className="text-ink-soft truncate">{account.email || "Unknown account"}</div>
                <div
                  className={clsx(
                    "text-[11.5px] truncate",
                    account.error ? "text-bad" : "text-faint",
                  )}
                >
                  {account.error
                    ? account.error
                    : account.has_send_scope
                      ? "Read, send, and calendar access"
                      : "Read and calendar access"}
                </div>
              </div>
              <button
                type="button"
                aria-label={`Remove ${account.email || account.token_file}`}
                onClick={() => void onRemove(account)}
                disabled={pendingId === `gmail:${account.token_file}`}
                className="grid place-items-center w-7 h-7 rounded-md text-muted hover:bg-surface hover:text-bad transition-colors disabled:opacity-50"
              >
                {pendingId === `gmail:${account.token_file}` ? (
                  <Loader2 size={14} strokeWidth={1.8} className="animate-spin" />
                ) : (
                  <Trash2 size={14} strokeWidth={1.8} />
                )}
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function ServiceCard({
  connectedServices,
  setupServices,
  editingId,
  serviceKey,
  pendingId,
  onEdit,
  onCancel,
  onKeyChange,
  onConnect,
  onDisconnect,
}: {
  connectedServices: ServiceConnection[];
  setupServices: ServiceConnection[];
  editingId: string | null;
  serviceKey: string;
  pendingId: string | null;
  onEdit: (service: ServiceConnection) => void;
  onCancel: () => void;
  onKeyChange: (value: string) => void;
  onConnect: (service: ServiceConnection) => Promise<void>;
  onDisconnect: (service: ServiceConnection) => Promise<void>;
}) {
  return (
    <section className="rounded-[12px] border border-line-soft bg-surface overflow-hidden">
      <div className="px-3.5 py-3 border-b border-line-soft">
        <div className="flex items-center gap-2">
          <MessageCircle size={14} strokeWidth={1.8} className="text-muted" />
          <div className="text-[13.5px] font-medium text-ink">Slack</div>
        </div>
        <div className="mt-1 text-[12px] text-faint leading-[1.4]">
          Token-backed Slack tools. OAuth MCP servers stay in the MCP tab.
        </div>
      </div>

      {connectedServices.length + setupServices.length === 0 ? (
        <div className="px-3.5 py-3 text-[12.5px] text-faint">No token-backed services are registered.</div>
      ) : (
        <div className="grid gap-3 px-3.5 py-3">
          <ServiceSection title="Ready" empty="No Slack tokens connected.">
            {connectedServices.map((service) => (
              <ServiceRow
                key={service.id}
                service={service}
                editing={editingId === service.id}
                serviceKey={editingId === service.id ? serviceKey : ""}
                pending={pendingId === service.id}
                onEdit={() => onEdit(service)}
                onCancel={onCancel}
                onKeyChange={onKeyChange}
                onConnect={() => void onConnect(service)}
                onDisconnect={() => void onDisconnect(service)}
              />
            ))}
          </ServiceSection>
          <ServiceSection title="Set up" empty="All Slack token services are connected.">
            {setupServices.map((service) => (
              <ServiceRow
                key={service.id}
                service={service}
                editing={editingId === service.id}
                serviceKey={editingId === service.id ? serviceKey : ""}
                pending={pendingId === service.id}
                onEdit={() => onEdit(service)}
                onCancel={onCancel}
                onKeyChange={onKeyChange}
                onConnect={() => void onConnect(service)}
                onDisconnect={() => void onDisconnect(service)}
              />
            ))}
          </ServiceSection>
        </div>
      )}
    </section>
  );
}

function ServiceSection({
  title,
  empty,
  children,
}: {
  title: string;
  empty: string;
  children: ReactNode;
}) {
  const childCount = Array.isArray(children) ? children.length : children ? 1 : 0;
  return (
    <section className="grid gap-2">
      <div className="text-[11.5px] font-semibold uppercase tracking-[0.08em] text-faint">{title}</div>
      {childCount > 0 ? (
        <div className="grid gap-2">{children}</div>
      ) : (
        <div className="rounded-[9px] border border-line-soft bg-surface-soft/45 px-3 py-2 text-[12.5px] text-faint">
          {empty}
        </div>
      )}
    </section>
  );
}

function ServiceRow({
  service,
  editing,
  serviceKey,
  pending,
  onEdit,
  onCancel,
  onKeyChange,
  onConnect,
  onDisconnect,
}: {
  service: ServiceConnection;
  editing: boolean;
  serviceKey: string;
  pending: boolean;
  onEdit: () => void;
  onCancel: () => void;
  onKeyChange: (value: string) => void;
  onConnect: () => void;
  onDisconnect: () => void;
}) {
  const actionLabel = pending ? "Working…" : serviceActionLabel(service);
  const readOnly = service.connected && service.from_env;
  const connectionPill = serviceConnectionPill(service);

  return (
    <div className="rounded-[10px] border border-line-soft bg-surface overflow-hidden">
      <div className="flex flex-wrap items-start gap-3 px-3 py-2.5">
        <div className="min-w-[150px] flex-1 grid gap-1">
          <div className="flex items-center gap-2 min-w-0">
            <ProviderDot connected={service.connected} />
            <div className="text-[13px] font-medium text-ink-soft truncate">{service.name}</div>
          </div>
          {connectionPill && <div className="text-[12px] text-muted font-mono truncate">{connectionPill}</div>}
        </div>
        <div className="ml-auto flex justify-end">
          {readOnly ? (
            <span className="inline-flex items-center h-8 px-3 rounded-md border border-line-soft bg-surface-soft text-[12.5px] font-medium text-muted">
              {actionLabel}
            </span>
          ) : (
            <button
              type="button"
              onClick={service.connected ? onDisconnect : onEdit}
              disabled={pending}
              className={clsx(
                "h-8 px-3 rounded-md text-[12.5px] font-medium transition-colors disabled:opacity-50",
                service.connected
                  ? "border border-line bg-surface text-ink-soft hover:border-line-strong"
                  : "bg-ink text-on-ink hover:opacity-90",
              )}
            >
              {actionLabel}
            </button>
          )}
        </div>
      </div>

      {editing && !service.connected && (
        <div className="grid grid-cols-[minmax(0,1fr)_auto_auto] gap-2 px-3 py-3 bg-surface-soft/35">
          <input
            type="password"
            value={serviceKey}
            onChange={(event) => onKeyChange(event.target.value)}
            placeholder="Token"
            autoFocus
            className="h-9 px-3 rounded-[9px] border border-line bg-surface text-[13.5px] text-ink outline-none hover:border-line-strong focus:border-accent focus:shadow-[0_0_0_3px_var(--color-accent-soft)] transition-[border-color,box-shadow]"
          />
          <button
            type="button"
            onClick={onConnect}
            disabled={!serviceKey.trim() || pending}
            className="h-9 px-3 rounded-[9px] bg-ink text-on-ink text-[12.5px] font-medium hover:opacity-90 disabled:opacity-40 transition-opacity"
          >
            Connect
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="h-9 px-3 rounded-[9px] border border-line bg-surface text-[12.5px] text-muted hover:text-ink hover:border-line-strong transition-colors"
          >
            Cancel
          </button>
        </div>
      )}
    </div>
  );
}

function GoogleIcon({ enabled }: { enabled: boolean }) {
  return (
    <span className="relative grid place-items-center w-4 h-4 shrink-0">
      <Mail size={14} strokeWidth={1.8} className={enabled ? "text-ok" : "text-muted"} />
      <CalendarDays
        size={9}
        strokeWidth={1.9}
        className={clsx("absolute -right-1 -bottom-0.5", enabled ? "text-ok" : "text-faint")}
      />
    </span>
  );
}

function ProviderDot({ connected }: { connected: boolean }) {
  if (connected) {
    return <CheckCircle2 size={14} strokeWidth={2} className="text-ok shrink-0" />;
  }
  return <KeyRound size={14} strokeWidth={1.8} className="text-faint shrink-0" />;
}
