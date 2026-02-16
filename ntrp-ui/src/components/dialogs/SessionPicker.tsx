import { useState, useCallback, useEffect, useRef } from "react";
import { useKeypress, type Key } from "../../hooks/index.js";
import { Dialog, BaseSelectionList, Hints } from "../ui/index.js";
import { colors } from "../ui/colors.js";
import type { Config } from "../../types.js";
import { listSessions, type SessionListItem } from "../../api/client.js";
import { formatAge } from "../../lib/utils.js";

interface SessionPickerProps {
  config: Config;
  currentSessionId: string | null;
  onSwitch: (sessionId: string) => void;
  onDelete: (sessionId: string) => Promise<void>;
  onNew: () => void;
  onClose: () => void;
}

export function SessionPicker({ config, currentSessionId, onSwitch, onDelete, onNew, onClose }: SessionPickerProps) {
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const mountedRef = useRef(true);
  const loadingRef = useRef(false);
  const deletingRef = useRef(false);
  const initializedRef = useRef(false);

  useEffect(() => () => { mountedRef.current = false; }, []);

  const loadSessions = useCallback(async () => {
    if (loadingRef.current) return;
    loadingRef.current = true;
    try {
      const { sessions: list } = await listSessions(config);
      if (!mountedRef.current) return;
      setSessions(list);
      if (!initializedRef.current) {
        const currentIdx = list.findIndex(s => s.session_id === currentSessionId);
        if (currentIdx >= 0) setSelectedIndex(currentIdx);
        initializedRef.current = true;
      } else {
        setSelectedIndex(prev => Math.min(prev, Math.max(0, list.length - 1)));
      }
    } catch {
      // ignore
    } finally {
      loadingRef.current = false;
    }
  }, [config, currentSessionId]);

  useEffect(() => { loadSessions(); }, [loadSessions]);

  const handleKeypress = useCallback(
    (key: Key) => {
      if (confirmDelete) {
        if (key.name === "y" && !deletingRef.current) {
          const target = sessions[selectedIndex];
          if (target) {
            deletingRef.current = true;
            onDelete(target.session_id)
              .then(() => { if (mountedRef.current) loadSessions(); })
              .finally(() => { deletingRef.current = false; });
          }
        }
        setConfirmDelete(false);
        return;
      }

      if (key.name === "escape") {
        onClose();
        return;
      }
      if (key.name === "return") {
        const target = sessions[selectedIndex];
        if (target && target.session_id !== currentSessionId) {
          onSwitch(target.session_id);
        }
        onClose();
        return;
      }
      if (key.name === "up" || (key.ctrl && key.name === "p")) {
        setSelectedIndex(i => Math.max(0, i - 1));
        return;
      }
      if (key.name === "down" || (key.ctrl && key.name === "n")) {
        setSelectedIndex(i => Math.min(Math.max(0, sessions.length - 1), i + 1));
        return;
      }
      if (key.name === "n" && !key.ctrl) {
        onNew();
        onClose();
        return;
      }
      if (key.name === "d" && !key.ctrl && !deletingRef.current) {
        setConfirmDelete(true);
        return;
      }
    },
    [selectedIndex, sessions, confirmDelete, onSwitch, onDelete, onNew, onClose, loadSessions]
  );

  useKeypress(handleKeypress, { isActive: true });

  const footer = confirmDelete ? (
    <Hints items={[["y", "confirm delete"], ["any", "cancel"]]} />
  ) : (
    <Hints items={[["↑↓", "navigate"], ["enter", "switch"], ["n", "new"], ["d", "delete"], ["esc", "close"]]} />
  );

  return (
    <Dialog title="Sessions" size="medium" onClose={onClose} footer={footer}>
      {({ height }) =>
        sessions.length === 0 ? (
          <text><span fg={colors.text.disabled}>No sessions</span></text>
        ) : (
          <BaseSelectionList
            items={sessions}
            selectedIndex={selectedIndex}
            visibleLines={height}
            showScrollArrows
            renderItem={(session, ctx) => {
              const isCurrent = session.session_id === currentSessionId;
              const label = session.name || session.session_id;
              const age = formatAge(session.last_activity);
              const msgs = session.message_count ?? 0;

              return (
                <box flexDirection="row" gap={1}>
                  <text>
                    <span fg={ctx.colors.text}>
                      {label}{isCurrent ? " (current)" : ""}
                    </span>
                  </text>
                  <text>
                    <span fg={colors.text.disabled}>
                      {msgs} msgs · {age}
                    </span>
                  </text>
                </box>
              );
            }}
          />
        )
      }
    </Dialog>
  );
}
