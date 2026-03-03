import { useState, useCallback, useEffect, useRef, useMemo } from "react";
import { useKeypress, type Key } from "../../hooks/index.js";
import { Dialog, SelectList, Hints, type SelectKeybind, type SelectOption } from "../ui/index.js";
import { colors } from "../ui/colors.js";
import type { Config } from "../../types.js";
import { listSessions, listArchivedSessions, type SessionListItem } from "../../api/client.js";
import { formatAge } from "../../lib/utils.js";

interface SessionPickerProps {
  config: Config;
  currentSessionId: string | null;
  onSwitch: (sessionId: string) => void;
  onDelete: (sessionId: string) => Promise<void>;
  onRestore: (sessionId: string) => Promise<void>;
  onPermanentDelete: (sessionId: string) => Promise<void>;
  onNew: () => void;
  onClose: () => void;
}

export function SessionPicker({ config, currentSessionId, onSwitch, onDelete, onRestore, onPermanentDelete, onNew, onClose }: SessionPickerProps) {
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [archivedSessions, setArchivedSessions] = useState<SessionListItem[]>([]);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const mountedRef = useRef(true);
  const loadingRef = useRef(false);
  const deletingRef = useRef(false);
  const [initialized, setInitialized] = useState(false);

  useEffect(() => () => { mountedRef.current = false; }, []);

  const loadSessions = useCallback(async () => {
    if (loadingRef.current) return;
    loadingRef.current = true;
    try {
      const { sessions: list } = await listSessions(config);
      if (!mountedRef.current) return;
      setSessions(list);
      setInitialized(true);
    } catch {
    } finally {
      loadingRef.current = false;
    }
  }, [config]);

  const loadArchived = useCallback(async () => {
    try {
      const { sessions: list } = await listArchivedSessions(config);
      if (!mountedRef.current) return;
      setArchivedSessions(list);
    } catch {
    }
  }, [config]);

  useEffect(() => { loadSessions(); }, [loadSessions]);

  const displaySessions = showArchived ? archivedSessions : sessions;

  const options: SelectOption[] = useMemo(() =>
    displaySessions.map(s => ({
      value: s.session_id,
      title: s.name || s.session_id,
      description: `${s.message_count ?? 0} msgs · ${showArchived ? `archived ${formatAge(s.archived_at!)}` : formatAge(s.last_activity)}`,
      indicator: !showArchived && s.session_id === currentSessionId ? "(current)" : undefined,
    })),
    [displaySessions, showArchived, currentSessionId],
  );

  const initialIndex = useMemo(() => {
    if (showArchived) return 0;
    const idx = sessions.findIndex(s => s.session_id === currentSessionId);
    return Math.max(0, idx);
  }, [sessions, currentSessionId, showArchived]);

  const activeKeybinds: SelectKeybind[] = useMemo(() => [
    { key: "n", label: "new", action: () => { onNew(); onClose(); } },
    { key: "d", label: "archive", action: (opt) => { setDeleteTarget(opt.value); setConfirmDelete(true); } },
    { key: "a", label: "archived", action: () => { setShowArchived(true); loadArchived(); } },
  ], [onNew, onClose, loadArchived]);

  const archivedKeybinds: SelectKeybind[] = useMemo(() => [
    { key: "r", label: "restore", action: (opt) => { onRestore(opt.value).then(() => { if (mountedRef.current) loadArchived(); }); } },
    { key: "d", label: "delete", action: (opt) => { setDeleteTarget(opt.value); setConfirmDelete(true); } },
    { key: "a", label: "back", action: () => setShowArchived(false) },
  ], [onRestore, loadArchived]);

  const handleConfirmKey = useCallback((key: Key) => {
    if (key.sequence === "y" && deleteTarget && !deletingRef.current) {
      deletingRef.current = true;
      const action = showArchived
        ? onPermanentDelete(deleteTarget).then(() => { if (mountedRef.current) loadArchived(); })
        : onDelete(deleteTarget).then(() => { if (mountedRef.current) loadSessions(); });
      action.finally(() => { deletingRef.current = false; });
    }
    setConfirmDelete(false);
    setDeleteTarget(null);
  }, [deleteTarget, showArchived, onPermanentDelete, onDelete, loadArchived, loadSessions]);

  useKeypress(handleConfirmKey, { isActive: confirmDelete });

  const footer = confirmDelete
    ? <Hints items={[["y", showArchived ? "confirm permanent delete" : "confirm archive"], ["any", "cancel"]]} />
    : undefined;

  return (
    <Dialog title={showArchived ? "Archived Sessions" : "Sessions"} size="medium" onClose={onClose} footer={footer}>
      {({ height }) => (
        <SelectList
          key={`${showArchived}-${initialized}`}
          options={options}
          keybinds={showArchived ? archivedKeybinds : activeKeybinds}
          visibleLines={height}
          initialIndex={initialIndex}
          isActive={!confirmDelete}
          emptyMessage={showArchived ? "No archived sessions" : "No sessions"}
          onSelect={showArchived ? () => {} : (opt) => {
            if (opt.value !== currentSessionId) onSwitch(opt.value);
            onClose();
          }}
          onClose={onClose}
          renderItem={(opt, ctx) => (
            <box flexDirection="row" gap={1}>
              <text>
                <span fg={ctx.colors.text}>
                  {opt.title}{opt.indicator ? ` ${opt.indicator}` : ""}
                </span>
              </text>
              <text>
                <span fg={colors.text.disabled}>{opt.description}</span>
              </text>
            </box>
          )}
        />
      )}
    </Dialog>
  );
}
