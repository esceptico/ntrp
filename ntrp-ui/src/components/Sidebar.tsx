import React, { useState, useEffect, useMemo } from "react";
import { colors } from "./ui/colors.js";
import { truncateText, formatAge } from "../lib/utils.js";
import { useAccentColor, type SessionNotification } from "../hooks/index.js";
import type { ServerConfig, Automation } from "../api/client.js";
import type { SidebarData } from "../hooks/useSidebar.js";

interface UsageData {
  prompt: number;
  completion: number;
  cache_read: number;
  cache_write: number;
  cost: number;
  lastCost: number;
}

interface SidebarProps {
  serverConfig: ServerConfig | null;
  serverVersion: string | null;
  serverUrl: string;
  data: SidebarData;
  usage: UsageData;
  width: number;
  height: number;
  currentSessionId: string | null;
  currentSessionName: string | null;
  sessionStates?: Map<string, SessionNotification>;
}

const H = colors.text.secondary; // header (brighter)
const D = colors.text.disabled;  // dim content
const S = colors.text.muted;     // secondary content

function SectionHeader({ label }: { label: string }) {
  return (
    <text>
      <span fg={H}>{label}</span>
    </text>
  );
}

function formatModel(model?: string | null): string {
  if (!model) return "—";
  const parts = model.split("/");
  return parts[parts.length - 1];
}

function formatTokens(total: number | null, pad?: number): string {
  let s: string;
  if (!total) s = "0";
  else if (total >= 1_000_000) s = `${(total / 1_000_000).toFixed(1)}M`;
  else if (total >= 1_000) s = `${(total / 1_000).toFixed(1)}k`;
  else s = `${total}`;
  return pad ? s.padStart(pad) : s;
}

function formatCost(cost: number): string {
  return `$${cost.toFixed(2)}`;
}

function ContextBar({ total, limit, width }: { total: number | null; limit: number; width: number }) {
  if (!total || !limit) {
    return <text><span fg={D}>no context</span></text>;
  }

  const pct = Math.min(1, total / limit);
  const barWidth = Math.max(4, width - 5); // " NNN%"
  const filled = Math.round(pct * barWidth);
  const empty = barWidth - filled;
  const pctStr = `${Math.round(pct * 100)}%`;

  const barColor = pct > 0.8 ? colors.text.primary : pct > 0.5 ? colors.text.secondary : D;

  return (
    <text>
      <span fg={barColor}>{"\u2588".repeat(filled)}</span>
      <span fg={colors.border}>{"\u2591".repeat(empty)}</span>
      <span fg={S}> {pctStr}</span>
    </text>
  );
}

interface SourceEntry { key: string; label: string; on: boolean; error?: boolean }

function getSourceEntries(cfg: ServerConfig): SourceEntry[] {
  const sources = cfg.sources;
  return [
    { key: "vault", label: "notes", on: !!cfg.has_notes },
    { key: "gmail", label: "gmail", on: !!sources?.gmail?.enabled && !!sources?.gmail?.connected, error: !!sources?.gmail?.error },
    { key: "calendar", label: "cal", on: !!sources?.calendar?.enabled && !!sources?.calendar?.connected, error: !!sources?.calendar?.error },
    { key: "browser", label: "browser", on: !!cfg.has_browser },
    { key: "memory", label: "memory", on: !!sources?.memory?.enabled },
    { key: "web", label: "web", on: !!sources?.web?.connected },
  ];
}

function SourcesList({ cfg }: { cfg: ServerConfig }) {
  const entries = getSourceEntries(cfg);
  return (
    <box flexDirection="column">
      {entries.map(({ key, label, on, error }) => {
        const color = error ? colors.status.error : on ? S : D;
        return (
          <text key={key}>
            <span fg={color}>{error ? "!" : on ? "\u2022" : "\u00B7"}</span>
            <span fg={color}> {label}</span>
          </text>
        );
      })}
    </box>
  );
}

function formatRelativeTime(isoStr: string): string {
  const target = new Date(isoStr).getTime();
  const now = Date.now();
  const diff = target - now;

  if (diff < 0) return "now";

  const mins = Math.floor(diff / 60_000);
  if (mins < 60) return `${mins}m`;

  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;

  const days = Math.floor(hours / 24);
  return `${days}d`;
}

function AutomationRow({ automation, width }: { automation: Automation; width: number }) {
  const time = automation.trigger.type === "time"
    ? (() => {
        let base = automation.trigger.every ? `every ${automation.trigger.every}` : automation.trigger.at ?? "";
        if (automation.trigger.start && automation.trigger.end) base += ` (${automation.trigger.start}\u2013${automation.trigger.end})`;
        return base;
      })()
    : `on:${automation.trigger.event_type}`;
  const eta = automation.next_run_at ? formatRelativeTime(automation.next_run_at) : "";
  const prefix = `${time} `;
  const suffix = eta ? ` ${eta}` : "";
  const nameWidth = Math.max(4, width - prefix.length - suffix.length);
  const name = truncateText(automation.name || automation.description, nameWidth);

  return (
    <text>
      <span fg={D}>{prefix}</span>
      <span fg={S}>{name}</span>
      {suffix && <span fg={D}>{suffix}</span>}
    </text>
  );
}

function SessionRow({ session, isCurrent, glowColor, width }: { session: { session_id: string; name: string | null; message_count: number; last_activity: string }; isCurrent: boolean; glowColor?: string; width: number }) {
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

function getGlowColor(state: SessionNotification | undefined, accentValue: string, pulse: boolean): string | undefined {
  if (!state) return undefined;
  switch (state) {
    case "streaming": return pulse ? accentValue : D;
    case "done": return colors.status.success;
    case "approval": return colors.status.warning;
    case "error": return colors.status.error;
  }
}

export function Sidebar({ serverConfig, serverVersion, serverUrl, data, usage, width, height, currentSessionId, currentSessionName, sessionStates }: SidebarProps) {
  const { accentValue } = useAccentColor();
  const contentWidth = width - 2; // padding

  const hasStreaming = useMemo(() =>
    sessionStates ? [...sessionStates.values()].includes("streaming") : false,
  [sessionStates]);

  const [pulse, setPulse] = useState(true);
  useEffect(() => {
    if (!hasStreaming) { setPulse(true); return; }
    const id = setInterval(() => setPulse(p => !p), 800);
    return () => clearInterval(id);
  }, [hasStreaming]);

  const MAX_SESSIONS = 5;
  const visibleSessions = data.sessions.slice(0, MAX_SESSIONS);
  const overflowCount = Math.max(0, data.sessions.length - MAX_SESSIONS);

  return (
    <scrollbox
      width={width}
      height={height}
      style={{ scrollbarOptions: { visible: false } }}
    >
      <box flexDirection="column" paddingX={1} paddingTop={1} gap={1}>
      {/* Title */}
      <box flexDirection="column">
        <text>
          <span fg={accentValue}>ntrp</span>
          {serverVersion && <span fg={D}> v{serverVersion}</span>}
        </text>
        <text><span fg={D}>{truncateText(serverUrl, contentWidth)}</span></text>
      </box>

      {/* Models */}
      {serverConfig && (
        <box flexDirection="column">
          <SectionHeader label="MODELS" />
          {(["chat", "expl", "mem", "emb"] as const).map((label) => {
            const key = { chat: "chat_model", expl: "explore_model", mem: "memory_model", emb: "embedding_model" }[label] as keyof typeof serverConfig;
            const raw = (serverConfig[key] as string) ?? "";
            const isOAuth = raw.startsWith("oauth:");
            const display = formatModel(isOAuth ? raw.slice(6) : raw);
            return (
              <text key={label}>
                <span fg={D}>{label.padEnd(5)}</span>
                <span fg={S}>{truncateText(display, contentWidth - 5 - (isOAuth ? 4 : 0))}</span>
                {isOAuth && <span fg={D}> sub</span>}
              </text>
            );
          })}
        </box>
      )}

      {/* Context */}
      {data.context && (
        <box flexDirection="column">
          <SectionHeader label="CONTEXT" />
          <ContextBar total={data.context.total} limit={data.context.limit} width={contentWidth} />
          <text>
            <span fg={D}>{formatTokens(data.context.total)} / {formatTokens(data.context.limit)}</span>
          </text>
          <text>
            <span fg={D}>{data.context.message_count} msgs  {data.context.tool_count} tools</span>
          </text>
        </box>
      )}

      {/* Usage */}
      {(usage.prompt > 0 || usage.completion > 0) && (() => {
        const totalInput = usage.prompt + usage.cache_read + usage.cache_write;
        const hasCache = usage.cache_read > 0 || usage.cache_write > 0;
        const cachePct = totalInput > 0 ? Math.round((usage.cache_read / totalInput) * 100) : 0;

        return (
          <box flexDirection="column">
            <SectionHeader label="USAGE" />
            <text>
              <span fg={S}>{formatTokens(totalInput)}</span>
              <span fg={D}> ↑ </span>
              <span fg={S}>{formatTokens(usage.completion)}</span>
              <span fg={D}> ↓</span>
              {hasCache && <span fg={D}>  {cachePct}% cache</span>}
            </text>
            {usage.cost > 0 && (
              <text>
                <span fg={S}>{formatCost(usage.cost)}</span>
                {usage.lastCost > 0 && <span fg={D}>{` (+${formatCost(usage.lastCost)})`}</span>}
              </text>
            )}
          </box>
        );
      })()}

      {/* Memory */}
      {data.stats && (
        <box flexDirection="column">
          <SectionHeader label="MEMORY" />
          <text>
            <span fg={S}>{data.stats.fact_count}</span>
            <span fg={D}> facts</span>
          </text>
          <text>
            <span fg={S}>{data.stats.observation_count}</span>
            <span fg={D}> observations</span>
          </text>
        </box>
      )}

      {/* Sources */}
      {serverConfig && (
        <box flexDirection="column">
          <SectionHeader label="SOURCES" />
          <SourcesList cfg={serverConfig} />
        </box>
      )}

      {/* Automations */}
      {data.nextAutomations.length > 0 && (
        <box flexDirection="column">
          <SectionHeader label="NEXT UP" />
          {data.nextAutomations.map(s => (
            <AutomationRow key={s.task_id} automation={s} width={contentWidth} />
          ))}
        </box>
      )}

      {/* Sessions */}
      {visibleSessions.length > 0 && (
        <box flexDirection="column">
          <SectionHeader label="SESSIONS" />
          {visibleSessions.map((s) => (
            <SessionRow
              key={s.session_id}
              session={s}
              isCurrent={s.session_id === currentSessionId}
              glowColor={getGlowColor(sessionStates?.get(s.session_id), accentValue, pulse)}
              width={contentWidth}
            />
          ))}
          {overflowCount > 0 && (
            <text><span fg={D}>  +{overflowCount} more</span></text>
          )}
        </box>
      )}
      </box>
    </scrollbox>
  );
}
