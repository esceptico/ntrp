import clsx from "clsx";
import type { MCPServer } from "@/api";
import { BlurSwap } from "@/components/ui/BlurSwap";
import { LabeledField } from "@/features/settings/components/Field";

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-2 min-w-0">
      <span className="shrink-0 text-muted">{label}</span>
      <span className="truncate font-mono text-ink-soft" title={value}>
        {value}
      </span>
    </div>
  );
}

export function OAuthStatus({
  server,
  busy,
  onReauthenticate,
}: {
  server: MCPServer;
  busy: boolean;
  onReauthenticate: () => void;
}) {
  const expired = !server.connected && !!server.error;
  const status = server.connected ? "Connected" : expired ? "Tokens expired" : "Not connected";
  const dot = server.connected ? "bg-ok" : expired ? "bg-bad" : "bg-line";

  return (
    <LabeledField label="Auth">
      <div className="grid gap-2 rounded-md border border-line-soft bg-surface-soft px-3 py-2.5">
        <div className="flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <span aria-hidden className={clsx("w-1.5 h-1.5 rounded-full shrink-0", dot)} />
            <span className="text-sm font-medium text-ink">OAuth · {status}</span>
          </div>
          <button
            type="button"
            onClick={onReauthenticate}
            disabled={busy}
            className="h-7 px-2 rounded-md text-xs font-medium tracking-[-0.005em] text-ink-soft border border-line-soft hover:bg-surface hover:text-ink transition-[background-color,color,scale] duration-check ease-out active:scale-[0.97] disabled:opacity-[0.45]"
          >
            <BlurSwap swapKey={busy ? "busy" : server.connected ? "reauth" : "signin"} blur={2}>
              {busy ? "…" : server.connected ? "Re-authenticate" : "Sign in"}
            </BlurSwap>
          </button>
        </div>
        {(server.client_name || server.client_id || server.scope) && (
          <div className="grid gap-0.5 text-xs">
            {server.client_name && <DetailRow label="Client" value={server.client_name} />}
            {server.client_id && <DetailRow label="Client ID" value={server.client_id} />}
            {server.scope && <DetailRow label="Scope" value={server.scope} />}
          </div>
        )}
      </div>
    </LabeledField>
  );
}
