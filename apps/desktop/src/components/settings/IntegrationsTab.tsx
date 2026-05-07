import { useCallback, useEffect, useMemo, useState } from "react";
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
  gmailAccountSummary,
  serviceActionLabel,
  serviceConnectionLabel,
} from "../../lib/integrationConnection";
import {
  settingsErrorMessage,
  settingsErrorTitle,
  shouldShowLoadedSettingsContent,
} from "../../lib/settingsLoadState";

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
        <p className="m-0 text-[12.5px] text-muted leading-[1.45] max-w-[540px]">
          Connect the data and action providers ntrp can use as tools. Model providers stay in
          Providers; MCP servers stay in MCP.
        </p>
        <button
          type="button"
          onClick={() => void refresh()}
          disabled={loading}
          className="inline-flex items-center gap-1.5 h-8 px-2.5 rounded-md border border-line bg-surface text-[12px] text-ink-soft hover:border-line-strong transition-colors disabled:opacity-50"
        >
          <RefreshCw size={12} strokeWidth={1.8} className={clsx(loading && "animate-spin")} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="grid gap-0.5 px-3 py-2.5 rounded-[10px] bg-bad-soft border border-[rgba(184,68,43,0.16)]">
          <strong className="text-bad text-[12px] font-semibold">
            {settingsErrorTitle("integrations", hasLoadedData)}
          </strong>
          <span className="text-[12px] text-[#8a3220] leading-[1.4]">
            {settingsErrorMessage(error)}
          </span>
        </div>
      )}

      {loading && !hasLoadedData ? (
        <div className="text-[12.5px] text-faint">Loading integrations…</div>
      ) : !showContent ? (
        <ConnectionHint />
      ) : (
        <>
          <GoogleCard
            enabled={googleEnabled}
            accounts={gmailAccounts}
            pendingId={pendingId}
            onToggle={toggleGoogle}
            onAdd={addGoogleAccount}
            onRemove={removeGoogleAccount}
          />

          <ServiceCard
            services={slackServices}
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

function ConnectionHint() {
  return (
    <div className="rounded-[12px] border border-line-soft bg-surface px-3.5 py-3">
      <div className="text-[13px] font-medium text-ink">Connect the desktop to ntrp first</div>
      <div className="mt-1 text-[12px] text-muted leading-[1.45]">
        Check the server URL and API key in the Connection tab, then refresh this view.
      </div>
    </div>
  );
}

function GoogleCard({
  enabled,
  accounts,
  pendingId,
  onToggle,
  onAdd,
  onRemove,
}: {
  enabled: boolean;
  accounts: GmailAccount[];
  pendingId: string | null;
  onToggle: (enabled: boolean) => Promise<void>;
  onAdd: () => Promise<void>;
  onRemove: (account: GmailAccount) => Promise<void>;
}) {
  const pendingGoogle = pendingId === "google";
  const pendingAdd = pendingId === "gmail:add";

  return (
    <section className="rounded-[12px] border border-line-soft bg-surface overflow-hidden">
      <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-3 px-3.5 py-3">
        <div className="min-w-0 grid gap-1">
          <div className="flex items-center gap-2 min-w-0">
            <GoogleIcon enabled={enabled} />
            <div className="text-[13px] font-medium text-ink truncate">Google Workspace</div>
            <span
              className={clsx(
                "px-1.5 py-0.5 rounded-full text-[10.5px] font-medium",
                enabled ? "bg-ok-soft text-ok" : "bg-surface-soft text-faint",
              )}
            >
              {enabled ? "Enabled" : "Disabled"}
            </span>
          </div>
          <div className="text-[11.5px] text-faint leading-[1.4]">
            Gmail and Calendar share the same Google account token.
          </div>
          <div className="text-[11.5px] text-muted font-mono truncate">
            {gmailAccountSummary(accounts)}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void onAdd()}
            disabled={pendingAdd}
            className="h-8 px-2.5 rounded-md border border-line bg-surface text-[12px] text-ink-soft hover:border-line-strong transition-colors disabled:opacity-50"
          >
            {pendingAdd ? "Connecting…" : "Add account"}
          </button>
          <button
            type="button"
            onClick={() => void onToggle(!enabled)}
            disabled={pendingGoogle}
            className={clsx(
              "h-8 px-3 rounded-md text-[12px] font-medium transition-colors disabled:opacity-50",
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
        <div className="grid gap-1 px-3.5 py-2.5 border-t border-line-soft bg-surface-soft/35">
          {accounts.map((account) => (
            <div
              key={account.token_file}
              className="grid grid-cols-[minmax(0,1fr)_auto] gap-2 items-center text-[12px]"
            >
              <div className="min-w-0">
                <div className="text-ink-soft truncate">{account.email || "Unknown account"}</div>
                <div
                  className={clsx(
                    "text-[11px] truncate",
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
                  <Loader2 size={13} strokeWidth={1.8} className="animate-spin" />
                ) : (
                  <Trash2 size={13} strokeWidth={1.8} />
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
  services,
  editingId,
  serviceKey,
  pendingId,
  onEdit,
  onCancel,
  onKeyChange,
  onConnect,
  onDisconnect,
}: {
  services: ServiceConnection[];
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
          <div className="text-[13px] font-medium text-ink">Slack</div>
        </div>
        <div className="mt-1 text-[11.5px] text-faint leading-[1.4]">
          Token-backed Slack tools. OAuth MCP servers stay in the MCP tab.
        </div>
      </div>

      {services.length === 0 ? (
        <div className="px-3.5 py-3 text-[12px] text-faint">No token-backed services are registered.</div>
      ) : (
        <div className="divide-y divide-line-soft">
          {services.map((service) => (
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

  return (
    <div>
      <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-3 px-3.5 py-2.5">
        <div className="min-w-0 grid gap-1">
          <div className="flex items-center gap-2 min-w-0">
            <ProviderDot connected={service.connected} />
            <div className="text-[12.5px] font-medium text-ink-soft truncate">{service.name}</div>
            <span
              className={clsx(
                "px-1.5 py-0.5 rounded-full text-[10.5px] font-medium",
                service.connected ? "bg-ok-soft text-ok" : "bg-surface-soft text-faint",
              )}
            >
              {serviceConnectionLabel(service)}
            </span>
          </div>
        </div>
        {readOnly ? (
          <span className="inline-flex items-center h-8 px-3 rounded-md border border-line-soft bg-surface-soft text-[12px] font-medium text-muted">
            {actionLabel}
          </span>
        ) : (
          <button
            type="button"
            onClick={service.connected ? onDisconnect : onEdit}
            disabled={pending}
            className={clsx(
              "h-8 px-3 rounded-md text-[12px] font-medium transition-colors disabled:opacity-50",
              service.connected
                ? "border border-line bg-surface text-ink-soft hover:border-line-strong"
                : "bg-ink text-on-ink hover:opacity-90",
            )}
          >
            {actionLabel}
          </button>
        )}
      </div>

      {editing && !service.connected && (
        <div className="grid grid-cols-[minmax(0,1fr)_auto_auto] gap-2 px-3.5 py-3 border-t border-line-soft bg-surface-soft/35">
          <input
            type="password"
            value={serviceKey}
            onChange={(event) => onKeyChange(event.target.value)}
            placeholder="Token"
            autoFocus
            className="h-9 px-3 rounded-[9px] border border-line bg-surface text-[13px] text-ink outline-none hover:border-line-strong focus:border-accent focus:shadow-[0_0_0_3px_var(--color-accent-soft)] transition-[border-color,box-shadow]"
          />
          <button
            type="button"
            onClick={onConnect}
            disabled={!serviceKey.trim() || pending}
            className="h-9 px-3 rounded-[9px] bg-ink text-on-ink text-[12px] font-medium hover:opacity-90 disabled:opacity-40 transition-opacity"
          >
            Connect
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="h-9 px-3 rounded-[9px] border border-line bg-surface text-[12px] text-muted hover:text-ink hover:border-line-strong transition-colors"
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
      <Mail size={13} strokeWidth={1.8} className={enabled ? "text-ok" : "text-muted"} />
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
    return <CheckCircle2 size={13} strokeWidth={2} className="text-ok shrink-0" />;
  }
  return <KeyRound size={13} strokeWidth={1.8} className="text-faint shrink-0" />;
}
