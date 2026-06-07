import { useEffect, useRef, useState } from "react";
import { Archive, Pencil } from "lucide-react";
import clsx from "clsx";
import { renameSession, switchSession } from "../../actions";
import { ICON } from "../../lib/icons";
import { formatRelativePast } from "../../lib/format";
import { SessionStateIcon } from "./SessionStateIcon";
import { RowAction } from "./RowAction";

export function SessionRow({
  sessionId,
  name,
  lastActivity,
  active,
  streaming,
  unread,
  isChannel,
  isAgent,
  depth = 0,
  renaming,
  onStartRename,
  onCancelRename,
  onArchive,
  onContextMenu,
}: {
  sessionId: string;
  name: string | null;
  lastActivity: string;
  active: boolean;
  streaming: boolean;
  unread: boolean;
  isChannel: boolean;
  isAgent: boolean;
  depth?: number;
  renaming: boolean;
  onStartRename: () => void;
  onCancelRename: () => void;
  onArchive: () => void;
  onContextMenu: (e: React.MouseEvent) => void;
}) {
  const [draft, setDraft] = useState(name ?? "");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (renaming) {
      setDraft(name ?? "");
      requestAnimationFrame(() => inputRef.current?.select());
    }
  }, [renaming, name]);

  async function commitRename() {
    const trimmed = draft.trim();
    onCancelRename();
    if (!trimmed || trimmed === (name ?? "")) return;
    try {
      await renameSession(sessionId, trimmed);
    } catch {
      /* surfaced via store error elsewhere */
    }
  }

  if (renaming) {
    return (
      <div
        className="grid grid-cols-[16px_minmax(0,1fr)] items-center gap-2 w-full px-2 py-1 rounded-lg bg-surface-soft text-ink shadow-[var(--shadow-sm)]"
        style={depth > 0 ? { paddingLeft: 8 + depth * 16 } : undefined}
      >
        <span aria-hidden />
        <input
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => void commitRename()}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void commitRename();
            } else if (e.key === "Escape") {
              e.preventDefault();
              onCancelRename();
            }
          }}
          className="min-w-0 w-full bg-transparent border-0 p-0 text-base font-medium tracking-[-0.005em] text-ink outline-none"
        />
      </div>
    );
  }

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => void switchSession(sessionId)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          void switchSession(sessionId);
        }
      }}
      onContextMenu={onContextMenu}
      onDoubleClick={(e) => {
        e.preventDefault();
        onStartRename();
      }}
      data-streaming={streaming ? "true" : undefined}
      data-active={active ? "true" : undefined}
      data-depth={depth || undefined}
      style={depth > 0 ? { paddingLeft: 8 + depth * 16 } : undefined}
      className="app-row session-row group/row grid grid-cols-[16px_minmax(0,1fr)_auto] items-center gap-1.5 w-full px-2 py-0.5 rounded-lg text-ink-soft text-left cursor-pointer"
    >
      <SessionStateIcon streaming={streaming} unread={unread} isChannel={isChannel} isAgent={isAgent} />
      <span className="min-w-0 truncate text-base font-medium tracking-[-0.005em]">
        {name || "untitled"}
      </span>
      <span className="relative shrink-0 h-[22px] w-[56px]">
        {/* Default state: timestamp. Hover swaps to row actions. */}
        <span className="absolute inset-0 flex items-center justify-end pr-[5px] transition-opacity duration-row group-hover/row:opacity-0 pointer-events-none">
          <span
            className={clsx(
              "text-xs tabular-nums",
              active ? "text-muted" : "text-faint",
            )}
          >
            {formatRelativePast(lastActivity)}
          </span>
        </span>
        <span className="absolute inset-0 flex items-center justify-end gap-0.5 opacity-0 group-hover/row:opacity-100 transition-opacity duration-row">
          <RowAction
            icon={<Pencil size={ICON.SM} strokeWidth={2} />}
            label="Rename"
            onClick={onStartRename}
          />
          <RowAction
            icon={<Archive size={ICON.SM} strokeWidth={2} />}
            label="Archive"
            onClick={onArchive}
          />
        </span>
      </span>
    </div>
  );
}
