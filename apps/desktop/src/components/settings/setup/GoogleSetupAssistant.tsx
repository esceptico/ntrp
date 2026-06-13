import { useState } from "react";
import type { GooglePreflightResponse, GoogleServiceChoice, SetupStatus } from "../../../api";
import { addGmailAccountApi, getSetupStatusApi, preflightGoogleSetupApi, saveGoogleCredentialsApi } from "../../../api";
import { fetchServerConfig, updateServerConfig } from "../../../actions";
import { useStore } from "../../../store";
import { GOOGLE_SERVICE_OPTIONS, googleChoiceLabel } from "../../../lib/setupAssistant";
import { SettingsInlineError } from "../SettingsNotice";

export function GoogleSetupAssistant({ onDone }: { onDone: () => Promise<void> | void }) {
  const config = useStore((s) => s.config);
  const serverConfig = useStore((s) => s.serverConfig);
  const [serviceChoice, setServiceChoice] = useState<GoogleServiceChoice>("all");
  const [path, setPath] = useState("");
  const [jsonText, setJsonText] = useState("");
  const [preflight, setPreflight] = useState<GooglePreflightResponse | null>(null);
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);

  async function run(label: string, fn: () => Promise<void>) {
    setBusy(label);
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  const credentialsValid = Boolean(path.trim()) !== Boolean(jsonText.trim());

  async function saveCredentials() {
    await run("credentials", async () => {
      const payload = path.trim()
        ? { path: path.trim() }
        : { json: JSON.parse(jsonText) as unknown };
      await saveGoogleCredentialsApi(config, payload);
    });
  }

  async function checkPreflight() {
    await run("preflight", async () => {
      setPreflight(await preflightGoogleSetupApi(config, serviceChoice));
    });
  }

  async function connect() {
    await run("connect", async () => {
      await addGmailAccountApi(config, serviceChoice);
      if (!serverConfig?.google_enabled) {
        await updateServerConfig({ integrations: { google: true } });
      }
      await fetchServerConfig();
      setStatus(await getSetupStatusApi(config));
      setConnected(true);
    });
  }

  async function verify() {
    await run("verify", async () => {
      setStatus(await getSetupStatusApi(config));
    });
  }

  return (
    <div className="grid gap-4">
      {error && <SettingsInlineError title="Setup assistant error" message={error} />}

      <section className="grid gap-2">
        <div className="text-sm font-medium text-ink">1. Choose service</div>
        <div className="grid gap-2 sm:grid-cols-2">
          {GOOGLE_SERVICE_OPTIONS.map((option) => (
            <label key={option.value} className="rounded-[10px] border border-line-soft bg-surface-soft/35 px-3 py-2 text-sm">
              <input
                type="radio"
                name="google-service-choice"
                value={option.value}
                checked={serviceChoice === option.value}
                onChange={() => setServiceChoice(option.value)}
                className="mr-2"
              />
              <span className="font-medium text-ink-soft">{option.label}</span>
              <span className="block pl-5 text-xs text-muted">{option.detail}</span>
            </label>
          ))}
        </div>
      </section>

      <section className="grid gap-2">
        <div className="text-sm font-medium text-ink">2. Credentials</div>
        <p className="m-0 text-xs text-muted">Create a Google Cloud OAuth client of type Desktop app, download JSON, then paste it or provide a file path.</p>
        <input className="input-field" value={path} onChange={(e) => setPath(e.target.value)} placeholder="/Users/me/Downloads/client_secret.json" disabled={Boolean(jsonText.trim())} />
        <textarea className="input-field min-h-[100px]" value={jsonText} onChange={(e) => setJsonText(e.target.value)} placeholder='{"installed":{"client_id":"..."}}' disabled={Boolean(path.trim())} />
        <div className="flex justify-end">
          <button type="button" className="h-8 px-3 rounded-md bg-ink text-on-ink text-sm disabled:opacity-[0.45]" disabled={!credentialsValid || busy === "credentials"} onClick={() => void saveCredentials()}>
            {busy === "credentials" ? "Saving…" : "Save credentials"}
          </button>
        </div>
      </section>

      <section className="grid gap-2">
        <div className="text-sm font-medium text-ink">3. Preflight</div>
        <p className="m-0 text-xs text-muted">This repo has no IMAP/app-password Gmail path today, so ntrp uses Google OAuth.</p>
        <button type="button" className="h-8 px-3 rounded-md border border-line bg-surface text-sm justify-self-start" disabled={busy === "preflight"} onClick={() => void checkPreflight()}>
          {busy === "preflight" ? "Checking…" : `Preflight ${googleChoiceLabel(serviceChoice)}`}
        </button>
        {preflight && (
          <div className="rounded-[10px] border border-line-soft bg-surface-soft/35 px-3 py-2 text-xs text-muted grid gap-1">
            <div>Credentials: {preflight.credentials.path} · {preflight.credentials.valid ? "valid" : "not ready"}</div>
            <div>Scopes: {preflight.scopes.join(", ") || "none"}</div>
            {preflight.warnings.map((warning) => <div key={warning} className="text-warn">{warning}</div>)}
          </div>
        )}
      </section>

      <section className="grid gap-2">
        <div className="text-sm font-medium text-ink">4. Connect</div>
        <p className="m-0 text-xs text-muted">ntrp opens a browser and waits for the local OAuth redirect.</p>
        <button type="button" className="h-8 px-3 rounded-md bg-ink text-on-ink text-sm justify-self-start disabled:opacity-[0.45]" disabled={busy === "connect"} onClick={() => void connect()}>
          {busy === "connect" ? "Connecting…" : "Connect Google account"}
        </button>
      </section>

      <section className="grid gap-2">
        <div className="text-sm font-medium text-ink">5. Verify</div>
        <button type="button" className="h-8 px-3 rounded-md border border-line bg-surface text-sm justify-self-start" disabled={busy === "verify"} onClick={() => void verify()}>
          {busy === "verify" ? "Refreshing…" : "Refresh setup status"}
        </button>
        {status && (
          <div className="rounded-[10px] border border-line-soft bg-surface-soft/35 px-3 py-2 text-xs text-muted grid gap-1">
            {status.google.provider_statuses.map((provider) => <div key={provider.id}>{provider.label}: {provider.status} ({provider.tool_count} tools){provider.detail ? ` · ${provider.detail}` : ""}</div>)}
            {status.google.accounts.map((account) => <div key={account.token_file}>Account: {account.email ?? account.token_file}</div>)}
            {status.google.calendar_tokens.map((token) => <div key={token.token_file}>Calendar token: {token.token_file} · {token.has_calendar_scope ? "calendar scope" : "missing scope"}</div>)}
          </div>
        )}
        {connected && (
          <button type="button" className="h-8 px-3 rounded-md bg-ink text-on-ink text-sm justify-self-end" onClick={() => void onDone()}>
            Done
          </button>
        )}
      </section>
    </div>
  );
}
