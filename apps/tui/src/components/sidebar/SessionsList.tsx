import { useState, useEffect, useMemo } from "react";
import { colors } from "../ui/colors.js";
import { truncateText, formatAge } from "../../lib/utils.js";
import { useAccentColor, type SessionNotification } from "../../hooks/index.js";
import { SectionHeader, H, D, S } from "./shared.js";

function parseHex(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

function lerpColor(a: string, b: string, t: number): string {
  const [ar, ag, ab] = parseHex(a);
  const [br, bg, bb] = parseHex(b);
  const r = Math.round(ar + (br - ar) * t);
  const g = Math.round(ag + (bg - ag) * t);
  const bl = Math.round(ab + (bb - ab) * t);
  return `#${r.toString(16).padStart(2, "0")}${g.toString(16).padStart(2, "0")}${bl.toString(16).padStart(2, "0")}`;
}

function getGlowColor(state: SessionNotification | undefined, streamingColor: string): string | undefined {
  if (!state) return undefined;
  switch (state) {
    case "streaming": return streamingColor;
    case "done": return colors.status.success;
    case "approval": return colors.status.warning;
    case "error": return colors.status.error;
  }
}

interface SessionInfo {
  session_id: string;
  name: string | null;
  message_count: number;
  last_activity: string;
}

const MAX_SIDEBAR_SESSIONS = 8;

function visibleSessions(sessions: SessionInfo[], currentSessionId: string | null): SessionInfo[] {
  const visible = sessions.slice(0, MAX_SIDEBAR_SESSIONS);
  if (!currentSessionId || visible.some((session) => session.session_id === currentSessionId)) {
    return visible;
  }

  const current = sessions.find((session) => session.session_id === currentSessionId);
  if (!current) return visible;
  return [...visible.slice(0, MAX_SIDEBAR_SESSIONS - 1), current];
}

function SessionRow({ session, isCurrent, glowColor, width }: { session: SessionInfo; isCurrent: boolean; glowColor?: string; width: number }) {
  const indicator = isCurrent ? "\u25B8 " : "  ";
  const label = session.name || session.session_id;
  const age = formatAge(session.last_activity);
  const suffix = ` ${age}`;
  const nameWidth = Math.max(4, width - indicator.length - suffix.length);
  const displayName = truncateText(label, nameWidth);
  const nameColor = isCurrent ? H() : glowColor ?? S();

  return (
    <text>
      <span fg={isCurrent ? H() : D()}>{indicator}</span>
      <span fg={nameColor}>{displayName}</span>
      <span fg={D()}>{suffix}</span>
    </text>
  );
}

export function SessionsList({ sessions, currentSessionId, sessionStates, width, onSessionClick }: {
  sessions: SessionInfo[];
  currentSessionId: string | null;
  sessionStates?: Map<string, SessionNotification>;
  width: number;
  onSessionClick?: (sessionId: string) => void;
}) {
  const { accentValue } = useAccentColor();

  const hasStreaming = useMemo(() =>
    sessionStates ? [...sessionStates.values()].includes("streaming") : false,
  [sessionStates]);

  const [phase, setPhase] = useState(0);
  useEffect(() => {
    if (!hasStreaming) { setPhase(0); return; }
    const id = setInterval(() => setPhase(p => (p + 1) % 60), 50);
    return () => clearInterval(id);
  }, [hasStreaming]);

  const t = hasStreaming ? (Math.sin(phase * Math.PI * 2 / 60) + 1) / 2 : 1;
  const streamingColor = hasStreaming ? lerpColor(colors.text.disabled, accentValue, t) : accentValue;
  const visible = visibleSessions(sessions, currentSessionId);
  const hiddenCount = Math.max(0, sessions.length - visible.length);

  return (
    <box flexDirection="column">
      <SectionHeader label="SESSIONS" />
      {visible.map((s) => (
        <box key={s.session_id} onMouseDown={onSessionClick ? () => onSessionClick(s.session_id) : undefined}>
          <SessionRow
            session={s}
            isCurrent={s.session_id === currentSessionId}
            glowColor={getGlowColor(sessionStates?.get(s.session_id), streamingColor)}
            width={width}
          />
        </box>
      ))}
      {hiddenCount > 0 && (
        <text><span fg={D()}>+{hiddenCount} more in /sessions</span></text>
      )}
    </box>
  );
}
