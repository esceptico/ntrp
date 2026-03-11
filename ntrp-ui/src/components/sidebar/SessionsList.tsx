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
    case "done": return streamingColor;
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

function SessionRow({ session, isCurrent, glowColor, width }: { session: SessionInfo; isCurrent: boolean; glowColor?: string; width: number }) {
  const indicator = isCurrent ? "\u25B8 " : "  ";
  const label = session.name || session.session_id;
  const age = formatAge(session.last_activity);
  const suffix = ` ${age}`;
  const nameWidth = Math.max(4, width - indicator.length - suffix.length);
  const displayName = truncateText(label, nameWidth);
  const nameColor = isCurrent ? H : glowColor ?? S;

  return (
    <text>
      <span fg={isCurrent ? H : D}>{indicator}</span>
      <span fg={nameColor}>{displayName}</span>
      <span fg={D}>{suffix}</span>
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

  return (
    <box flexDirection="column">
      <SectionHeader label="SESSIONS" />
      {sessions.map((s) => (
        <box key={s.session_id} onMouseDown={onSessionClick ? () => onSessionClick(s.session_id) : undefined}>
          <SessionRow
            session={s}
            isCurrent={s.session_id === currentSessionId}
            glowColor={getGlowColor(sessionStates?.get(s.session_id), streamingColor)}
            width={width}
          />
        </box>
      ))}
    </box>
  );
}
