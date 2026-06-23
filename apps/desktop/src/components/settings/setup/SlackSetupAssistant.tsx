import { useState } from "react";
import type { SetupStatus, SlackVerifyResponse } from "../../../api";
import { connectServiceApi, getSetupStatusApi, verifySlackTokenApi } from "../../../api";
import { useStore } from "../../../store";
import { slackTokenPrefixValid, type SlackSetupServiceId } from "../../../lib/setupAssistant";
import { SettingsInlineError } from "../SettingsNotice";

export function SlackSetupAssistant({ onDone }: { onDone: () => Promise<void> | void }) {
  const config = useStore((s) => s.config);
  const [serviceId, setServiceId] = useState<SlackSetupServiceId>("slack_user_token");
  const [token, setToken] = useState("");
  const [verifyResult, setVerifyResult] = useState<SlackVerifyResponse | null>(null);
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const prefixValid = slackTokenPrefixValid(serviceId, token);

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

  async function verify() {
    await run("verify", async () => {
      setVerifyResult(await verifySlackTokenApi(config, serviceId, token.trim()));
    });
  }

  async function save() {
    await run("save", async () => {
      await connectServiceApi(config, serviceId, token.trim());
      setStatus(await getSetupStatusApi(config));
      setSaved(true);
    });
  }

  async function refresh() {
    await run("refresh", async () => {
      setStatus(await getSetupStatusApi(config));
    });
  }

  return (
    <div className="grid gap-4">
      {error && <SettingsInlineError title="Slack setup error" message={error} />}
      <section className="grid gap-2">
        <div className="text-sm font-medium text-ink">1. Choose token type</div>
        <p className="m-0 text-xs text-muted">Current setup is token paste; Slack OAuth install is not available until app/client config exists. User tokens start xoxp-, bot tokens start xoxb-.</p>
        <div className="flex flex-wrap gap-2">
          {[
            ["slack_user_token", "User token (xoxp-)"] as const,
            ["slack_bot_token", "Bot token (xoxb-)"] as const,
          ].map(([id, label]) => (
            <label key={id} className="rounded-md border border-line-soft bg-surface-soft/35 px-3 py-2 text-sm">
              <input type="radio" name="slack-service-choice" className="mr-2" checked={serviceId === id} onChange={() => setServiceId(id)} />{label}
            </label>
          ))}
        </div>
      </section>

      <section className="grid gap-2">
        <div className="text-sm font-medium text-ink">2. Paste token</div>
        <input className="input-field" type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder={serviceId === "slack_bot_token" ? "xoxb-..." : "xoxp-..."} />
        {token.trim() && !prefixValid && <div className="text-xs text-warn">Token prefix does not match the selected type.</div>}
        <div className="flex flex-wrap gap-2 justify-end">
          <button type="button" className="h-8 px-3 rounded-md border border-line bg-surface text-sm disabled:opacity-[0.45]" disabled={!prefixValid || busy === "verify"} onClick={() => void verify()}>
            {busy === "verify" ? "Verifying…" : "Verify token"}
          </button>
          <button type="button" className="h-8 px-3 rounded-md border border-line bg-surface text-sm disabled:opacity-[0.45]" disabled={!token.trim() || busy === "save"} onClick={() => void save()}>
            Save without verification
          </button>
          <button type="button" className="h-8 px-3 rounded-md bg-ink text-on-ink text-sm disabled:opacity-[0.45]" disabled={!prefixValid || busy === "save"} onClick={() => void save()}>
            {busy === "save" ? "Saving…" : "Save token"}
          </button>
        </div>
        {verifyResult && (
          <div className="rounded-[10px] border border-line-soft bg-surface-soft/35 px-3 py-2 text-xs text-muted">
            Verified {verifyResult.token_kind} token{verifyResult.team ? ` for ${verifyResult.team}` : ""}{verifyResult.user ? ` · user ${verifyResult.user}` : ""}{verifyResult.bot_id ? ` · bot ${verifyResult.bot_id}` : ""}. Verification checks the token, not every tool permission.
          </div>
        )}
      </section>

      <section className="grid gap-2">
        <div className="text-sm font-medium text-ink">3. Provider status</div>
        <button type="button" className="h-8 px-3 rounded-md border border-line bg-surface text-sm justify-self-start" disabled={busy === "refresh"} onClick={() => void refresh()}>
          {busy === "refresh" ? "Refreshing…" : "Refresh Slack status"}
        </button>
        {status && (
          <div className="rounded-[10px] border border-line-soft bg-surface-soft/35 px-3 py-2 text-xs text-muted grid gap-1">
            <div>Services: {status.slack.services.map((service) => `${service.name}: ${service.connected ? "token saved" : "not saved"}`).join(" · ") || "none"}</div>
            <div>Provider: {status.slack.provider_status ? `${status.slack.provider_status.status} (${status.slack.provider_status.tool_count} tools)` : "not available"}</div>
          </div>
        )}
        {saved && (
          <button type="button" className="h-8 px-3 rounded-md bg-ink text-on-ink text-sm justify-self-end" onClick={() => void onDone()}>
            Done
          </button>
        )}
      </section>
    </div>
  );
}
