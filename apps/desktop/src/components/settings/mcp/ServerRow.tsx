import { Settings as SettingsIcon } from "lucide-react";
import clsx from "clsx";
import { useStore } from "../../../store";
import { type MCPServer, startMCPOAuthApi, toggleMCPServerApi } from "../../../api";
import { useMountedRef, useMutationState } from "../../../lib/hooks";
import { ICON } from "../../../lib/icons";
import { GlassSwitch } from "../../GlassSwitch";

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
  const mounted = useMountedRef();
  const { busy, error, run } = useMutationState(mounted);

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
  else if (server.error) subtitleParts.push("error");
  else if (!server.enabled) subtitleParts.push("disabled");
  else subtitleParts.push("disconnected");

  return (
    <li className="flex items-center gap-3 px-3.5 py-2.5">
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
        {(error || server.error) && (
          <div
            className="mt-1 ml-3.5 text-xs text-bad truncate"
            title={error ?? server.error ?? ""}
          >
            {error ?? server.error}
          </div>
        )}
      </div>
      <div className="flex items-center gap-1 shrink-0">
        {needsAuth && (
          <button
            type="button"
            onClick={onAuthenticate}
            disabled={busy}
            className="h-7 px-2.5 rounded-md text-xs font-medium tracking-[-0.005em] text-ink-soft border border-line-soft hover:bg-surface-soft hover:text-ink transition-colors disabled:opacity-50"
          >
            {busy ? "…" : "Authenticate"}
          </button>
        )}
        <button
          type="button"
          onClick={onEdit}
          aria-label="Configure"
          className="grid place-items-center w-7 h-7 rounded-md text-muted hover:bg-surface-soft hover:text-ink transition-colors"
        >
          <SettingsIcon size={ICON.MD} strokeWidth={2} />
        </button>
        <GlassSwitch
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
