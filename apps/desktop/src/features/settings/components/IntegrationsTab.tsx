import { useCallback, useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import { RefreshCw } from "lucide-react";
import { addGmailAccountApi, connectServiceApi, disconnectServiceApi, listGmailAccountsApi, listServicesApi, removeGmailAccountApi, type GmailAccount, type ServiceConnection } from "@/api/settings";
import { fetchServerConfig, updateServerConfig } from "@/actions/server";
import { useStore } from "@/stores";
import { ReadinessCard } from "@/features/settings/components/ReadinessCard";
import { GoogleCard } from "@/features/settings/components/GoogleCard";
import { ServiceCard } from "@/features/settings/components/ServiceCard";
import { SettingsTabSkeleton } from "@/features/settings/components/SettingsTabSkeleton";
import {
  googleConnectionSummary,
} from "@/features/settings/lib/integrationConnection";
import {
  settingsErrorMessage,
  settingsErrorTitle,
  shouldShowLoadedSettingsContent,
} from "@/features/settings/lib/settingsLoadState";
import { SettingsConnectionHint, SettingsInlineError } from "@/features/settings/components/SettingsNotice";
import { ICON } from "@/lib/icons";
import { Button } from "@/components/ui/Button";
import { SetupAssistant, type SetupAssistantKind } from "@/features/settings/components/setup/SetupAssistant";

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
  const [assistant, setAssistant] = useState<Extract<SetupAssistantKind, "google" | "slack"> | null>(null);

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
  const readyToolsCount =
    (googleSummary.tone === "ready" ? 1 : 0) + connectedSlackServices.length;

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
        <p className="m-0 text-sm text-muted leading-[1.45] max-w-[540px]">
          Connect the data and action providers ntrp can use as tools. Model providers stay in
          Providers; MCP servers stay in MCP.
        </p>
        <Button variant="secondary" onClick={() => void refresh()} disabled={loading}>
          <RefreshCw size={ICON.SM} strokeWidth={2} className={clsx(loading && "animate-spin")} />
          Refresh
        </Button>
      </div>

      {error && (
        <SettingsInlineError
          title={settingsErrorTitle("integrations", hasLoadedData)}
          message={settingsErrorMessage(error)}
        />
      )}

      {loading && !hasLoadedData ? (
        <SettingsTabSkeleton variant="cards" label="Loading integrations…" />
      ) : !showContent ? (
        <SettingsConnectionHint />
      ) : (
        <>
          {assistant && (
            <SetupAssistant
              kind={assistant}
              onClose={() => setAssistant(null)}
              onDone={async () => {
                setAssistant(null);
                await fetchServerConfig();
                await refresh();
              }}
            />
          )}

          <ReadinessCard
            tone={readyToolsCount > 0 ? "ok" : "warn"}
            label={readyToolsCount > 0 ? "Tools ready" : "Connect tools"}
            detail={`Google: ${googleSummary.label} · Slack: ${connectedSlackServices.length || "none"}`}
            footnote="Tool integrations are optional, but connected tools become available to the agent."
          />

          <GoogleCard
            enabled={googleEnabled}
            summary={googleSummary}
            accounts={gmailAccounts}
            pendingId={pendingId}
            onToggle={toggleGoogle}
            onAdd={addGoogleAccount}
            onRemove={removeGoogleAccount}
            onAssistant={() => setAssistant("google")}
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
            onAssistant={() => setAssistant("slack")}
          />
        </>
      )}
    </div>
  );
}
