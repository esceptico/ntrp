import React from "react";
import { colors } from "./ui/colors.js";
import { truncateText } from "../lib/utils.js";
import { useAccentColor } from "../hooks/index.js";
import type { ServerConfig, Schedule } from "../api/client.js";
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
  data: SidebarData;
  usage: UsageData;
  width: number;
  height: number;
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

function formatModel(model: string): string {
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

interface SourceEntry { key: string; label: string; on: boolean }

function getSourceEntries(cfg: ServerConfig): SourceEntry[] {
  const sources = cfg.sources;
  return [
    { key: "vault", label: "notes", on: !!cfg.has_notes },
    { key: "gmail", label: "gmail", on: !!sources?.gmail?.enabled && !!sources?.gmail?.connected },
    { key: "calendar", label: "cal", on: !!sources?.calendar?.enabled && !!sources?.calendar?.connected },
    { key: "browser", label: "browser", on: !!cfg.has_browser },
    { key: "memory", label: "memory", on: !!sources?.memory?.enabled },
    { key: "web", label: "web", on: !!sources?.web?.connected },
  ];
}

function SourcesList({ cfg }: { cfg: ServerConfig }) {
  const entries = getSourceEntries(cfg);
  return (
    <box flexDirection="column">
      {entries.map(({ key, label, on }) => (
        <text key={key}>
          <span fg={on ? S : D}>{on ? "\u2022" : "\u00B7"}</span>
          <span fg={on ? S : D}> {label}</span>
        </text>
      ))}
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

function ScheduleRow({ schedule, width }: { schedule: Schedule; width: number }) {
  const time = schedule.time_of_day || "??:??";
  const eta = schedule.next_run_at ? formatRelativeTime(schedule.next_run_at) : "";
  const prefix = `${time} `;
  const suffix = eta ? ` ${eta}` : "";
  const nameWidth = Math.max(4, width - prefix.length - suffix.length);
  const name = truncateText(schedule.name || schedule.description, nameWidth);

  return (
    <text>
      <span fg={D}>{prefix}</span>
      <span fg={S}>{name}</span>
      {suffix && <span fg={D}>{suffix}</span>}
    </text>
  );
}

export function Sidebar({ serverConfig, data, usage, width, height }: SidebarProps) {
  const { accentValue } = useAccentColor();
  const contentWidth = width - 2; // padding

  return (
    <box
      flexDirection="column"
      width={width}
      height={height}
      paddingX={1}
      paddingTop={1}
      gap={1}
      overflow="hidden"
    >
      {/* Title */}
      <text>
        <span fg={accentValue}>ntrp</span>
        <span fg={D}> v0.1.0</span>
      </text>

      {/* Models */}
      {serverConfig && (
        <box flexDirection="column">
          <SectionHeader label="MODELS" />
          <text>
            <span fg={D}>chat </span>
            <span fg={S}>{truncateText(formatModel(serverConfig.chat_model), contentWidth - 5)}</span>
          </text>
          <text>
            <span fg={D}>expl </span>
            <span fg={S}>{truncateText(formatModel(serverConfig.explore_model), contentWidth - 5)}</span>
          </text>
          <text>
            <span fg={D}>mem  </span>
            <span fg={S}>{truncateText(formatModel(serverConfig.memory_model), contentWidth - 5)}</span>
          </text>
          <text>
            <span fg={D}>emb  </span>
            <span fg={S}>{truncateText(formatModel(serverConfig.embedding_model), contentWidth - 5)}</span>
          </text>
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
              <span fg={D}> ↓ </span>
              <span fg={S}>{formatTokens(usage.completion)}</span>
              <span fg={D}> ↑</span>
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

      {/* Schedules */}
      {data.nextSchedules.length > 0 && (
        <box flexDirection="column">
          <SectionHeader label="NEXT UP" />
          {data.nextSchedules.map(s => (
            <ScheduleRow key={s.task_id} schedule={s} width={contentWidth} />
          ))}
        </box>
      )}
    </box>
  );
}
