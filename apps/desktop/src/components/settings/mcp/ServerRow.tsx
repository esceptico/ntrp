import { Settings as SettingsIcon } from "lucide-react";
import clsx from "clsx";
import { useStore } from "../../../store";
import { type MCPServer, startMCPOAuthApi, toggleMCPServerApi } from "../../../api";
import { useMutationState } from "../../../lib/hooks";
import { ICON } from "../../../lib/icons";
import { IconButton } from "../../IconButton";
import { SwitchControl } from "../../SwitchControl";

export function ServerRow({
  server,
  onEdit,
  onChanged,
}: {
  server: MCPServer;
  onEdit: () => void;
  onChanged: () => Promise<void>;
}) {
  const config = useStore((s) => s.config);
  const { busy, error, run } = useMutationState();

  const onToggle = (next: boolean) =>
    void run(async () => {
      await toggleMCPServerApi(config, server.name, next);
      await onChanged();
    });

  const onAuthenticate = () =>
    void run(async () => {
      await startMCPOAuthApi(config, server.name);
      await onChanged();
    });

  const needsAuth = server.auth === "oauth" && !server.connected;
  const subtitleParts: string[] = [];
  subtitleParts.push(server.transport.toUpperCase());
  if (server.connected) subtitleParts.push(`${server.tool_count} tools`);
  else if (!server.enabled) subtitleParts.push("disabled");
  else if (needsAuth) subtitleParts.push(server.error ? "tokens expired" : "sign in needed");
  else if (server.error) subtitleParts.push("error");
  else subtitleParts.push("disconnected");

  return (
    <li className="flex min-w-0 items-center gap-2 px-3.5 py-2.5">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span
            aria-hidden
            className={clsx(
              "w-1.5 h-1.5 rounded-full shrink-0",
              server.connected ? "bg-ok" : server.error ? "bg-bad" : "bg-line",
            )}
          />
          <span className="text-base font-medium text-ink tracking-[-0.005em] truncate">
            {server.name}
          </span>
        </div>
        <div className="mt-0.5 ml-3.5 text-xs text-faint tabular-nums">
          {subtitleParts.join(" · ")}
        </div>
        {(error || (server.error && !needsAuth)) && (
          <div
            className="mt-1 ml-3.5 text-xs text-bad truncate"
            title={error ?? server.error ?? ""}
          >
            {error ?? server.error}
          </div>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {needsAuth && (
          <button
            type="button"
            onClick={onAuthenticate}
            disabled={busy}
            className="h-7 px-2 rounded-md text-xs font-medium tracking-[-0.005em] text-ink-soft border border-line-soft hover:bg-surface-soft hover:text-ink transition-colors disabled:opacity-50"
          >
            {busy ? "…" : server.error ? "Re-authenticate" : "Sign in"}
          </button>
        )}
        <IconButton onClick={onEdit} aria-label="Configure">
          <SettingsIcon size={ICON.MD} strokeWidth={2} />
        </IconButton>
        <SwitchControl
          size="sm"
          checked={server.enabled}
          onChange={onToggle}
          disabled={busy}
          aria-label={server.enabled ? `Disable ${server.name}` : `Enable ${server.name}`}
        />
      </div>
    </li>
  );
}
