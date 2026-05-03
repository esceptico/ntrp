import { Pencil, Settings as SettingsIcon } from "lucide-react";
import clsx from "clsx";
import { useStore } from "../store";
import { hostFromUrl } from "../api";
import { createSession, switchSession } from "../actions";

function formatAge(value: string): string {
  const delta = Date.now() - new Date(value).getTime();
  const minutes = Math.max(1, Math.floor(delta / 60_000));
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

function Brand() {
  const version = window.ntrpDesktop?.version?.() ?? "dev";
  return (
    <div className="flex items-center gap-2 px-4 pt-1 pb-3.5">
      <div className="brand-mark grid place-items-center w-6 h-6 rounded-[7px] text-[11px] font-bold tracking-tight">
        n
      </div>
      <span className="text-[13.5px] font-semibold tracking-tight text-ink">ntrp</span>
      <span className="ml-auto text-[10.5px] font-medium text-faint tracking-[0.02em]">
        v{version}
      </span>
    </div>
  );
}

function NavRow({
  icon,
  label,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center gap-[9px] w-full px-2 py-1.5 rounded-lg text-[13px] font-medium text-ink-soft text-left tracking-[-0.005em] hover:bg-[rgba(20,18,14,0.045)] transition-colors"
    >
      <span className="nav-icon grid place-items-center w-[22px] h-[22px] rounded-md text-ink-soft shrink-0">
        {icon}
      </span>
      <span>{label}</span>
    </button>
  );
}

function SessionList() {
  const sessions = useStore((s) => s.sessions);
  const currentSessionId = useStore((s) => s.currentSessionId);
  const connected = useStore((s) => s.connected);

  return (
    <>
      <div className="flex items-center justify-between px-[18px] pt-[22px] pb-1.5 text-[10.5px] font-medium uppercase tracking-[0.08em] text-faint">
        <span>Sessions</span>
        {sessions.length > 0 && <span>{sessions.length}</span>}
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto scroll-thin px-2.5 pb-3 flex flex-col gap-px">
        {sessions.length === 0 ? (
          <div className="px-3 py-3 text-[12px] italic text-faint">
            {connected ? "No sessions yet." : "Connect to load sessions."}
          </div>
        ) : (
          sessions.map((session) => (
            <button
              key={session.session_id}
              type="button"
              onClick={() => void switchSession(session.session_id)}
              className={clsx(
                "grid grid-cols-[minmax(0,1fr)_auto] items-center gap-2 w-full px-2.5 py-1.5 rounded-lg text-left transition-colors",
                session.session_id === currentSessionId
                  ? "bg-[rgba(20,18,14,0.07)] text-ink"
                  : "text-ink-soft hover:bg-[rgba(20,18,14,0.045)]",
              )}
            >
              <span className="text-[13px] font-medium tracking-[-0.005em] truncate">
                {session.name || "untitled"}
              </span>
              <span
                className={clsx(
                  "text-[11px] tabular-nums shrink-0",
                  session.session_id === currentSessionId ? "text-muted" : "text-faint",
                )}
              >
                {formatAge(session.last_activity)}
              </span>
            </button>
          ))
        )}
      </div>
    </>
  );
}

function ConnectionFooter() {
  const config = useStore((s) => s.config);
  const connected = useStore((s) => s.connected);
  const error = useStore((s) => s.error);
  const openSettings = useStore((s) => s.openSettings);

  const status = connected ? "Connected" : error ? "Connection error" : "Not connected";
  const dotClass = connected ? "bg-ok shadow-[0_0_0_3px_var(--color-ok-soft)]" : error ? "bg-bad shadow-[0_0_0_3px_var(--color-bad-soft)]" : "bg-warn shadow-[0_0_0_3px_var(--color-warn-soft)]";

  return (
    <div className="px-3 pt-2.5 pb-3.5">
      <button
        type="button"
        onClick={openSettings}
        title={error || (connected ? "Connected" : "Click to configure")}
        className="connection-pill flex items-center gap-2 w-full px-2.5 py-[7px] rounded-[9px] bg-surface text-[12px] text-left hover:bg-[#fcfbf8] transition-colors"
      >
        <span className={clsx("w-[7px] h-[7px] rounded-full shrink-0", dotClass)} />
        <span className="flex-1 min-w-0 grid gap-px">
          <span className="text-[12px] font-medium tracking-[-0.005em] text-ink">{status}</span>
          <span className="text-[11px] text-faint font-mono truncate">{hostFromUrl(config.serverUrl)}</span>
        </span>
        <span className="grid place-items-center w-[22px] h-[22px] text-muted shrink-0">
          <SettingsIcon size={13} strokeWidth={1.7} />
        </span>
      </button>
    </div>
  );
}

export function Sidebar() {
  const openSettings = useStore((s) => s.openSettings);

  return (
    <aside className="sidebar flex flex-col">
      <div className="drag-spacer shrink-0 h-[38px]" />
      <Brand />
      <nav className="flex flex-col gap-px px-2.5">
        <NavRow icon={<Pencil size={13} strokeWidth={1.7} />} label="New session" onClick={() => void createSession()} />
        <NavRow icon={<SettingsIcon size={13} strokeWidth={1.7} />} label="Settings" onClick={openSettings} />
      </nav>
      <SessionList />
      <ConnectionFooter />
    </aside>
  );
}
