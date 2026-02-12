import { useEffect, useState } from "react";
import { colors } from "../../ui/index.js";
import { useAccentColor } from "../../../hooks/index.js";
import { getStats, type Stats } from "../../../api/client.js";
import type { Config } from "../../../types.js";

interface StatsViewProps {
  config: Config;
  width: number;
}

function StatCard({ label, value, accentValue }: { label: string; value: number; accentValue: string }) {
  return (
    <box flexDirection="column" marginRight={4}>
      <text>
        <span fg={accentValue}><strong>{value.toLocaleString()}</strong></span>
      </text>
      <text><span fg={colors.text.muted}>{label}</span></text>
    </box>
  );
}

export function StatsView({ config, width }: StatsViewProps) {
  const { accentValue } = useAccentColor();
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getStats(config)
      .then(setStats)
      .catch(() => setStats(null))
      .finally(() => setLoading(false));
  }, [config]);

  if (loading) {
    return (
      <box flexDirection="column" width={width}>
        <text><span fg={colors.text.muted}>Loading stats...</span></text>
      </box>
    );
  }

  if (!stats) {
    return (
      <box flexDirection="column" width={width}>
        <text><span fg={colors.text.muted}>Failed to load stats</span></text>
      </box>
    );
  }

  const hasData = stats.fact_count > 0 || stats.observation_count > 0;

  return (
    <box flexDirection="column" width={width}>
      <text><span fg={colors.text.muted}>MEMORY OVERVIEW</span></text>

      <box flexDirection="row" marginTop={1} marginBottom={1}>
        <StatCard label="facts" value={stats.fact_count} accentValue={accentValue} />
        <StatCard label="observations" value={stats.observation_count} accentValue={accentValue} />
      </box>

      {!hasData && (
        <box marginY={1}>
          <text>
            <span fg={colors.text.secondary}>
              No memory data yet. Facts will appear as the system learns.
            </span>
          </text>
        </box>
      )}

    </box>
  );
}
