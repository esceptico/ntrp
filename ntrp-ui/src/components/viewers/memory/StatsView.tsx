import { useEffect, useState } from "react";
import { Box, Text } from "ink";
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
    <Box flexDirection="column" marginRight={4}>
      <Text color={accentValue} bold>
        {value.toLocaleString()}
      </Text>
      <Text color={colors.text.muted}>{label}</Text>
    </Box>
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
      <Box flexDirection="column" width={width}>
        <Text color={colors.text.muted}>Loading stats...</Text>
      </Box>
    );
  }

  if (!stats) {
    return (
      <Box flexDirection="column" width={width}>
        <Text color={colors.text.muted}>Failed to load stats</Text>
      </Box>
    );
  }

  const hasData = stats.fact_count > 0 || stats.observation_count > 0;

  return (
    <Box flexDirection="column" width={width}>
      <Text color={colors.text.muted}>MEMORY OVERVIEW</Text>

      <Box flexDirection="row" marginTop={1} marginBottom={1}>
        <StatCard label="facts" value={stats.fact_count} accentValue={accentValue} />
        <StatCard label="observations" value={stats.observation_count} accentValue={accentValue} />
        <StatCard label="links" value={stats.link_count} accentValue={accentValue} />
      </Box>

      {!hasData && (
        <Box marginY={1}>
          <Text color={colors.text.secondary}>
            No memory data yet. Facts will appear as the system learns.
          </Text>
        </Box>
      )}

      <Box height={1} />

      <Text color={colors.text.muted}>CONNECTED SOURCES</Text>
      <Box flexDirection="column" marginTop={1}>
        {stats.sources.length > 0 ? (
          stats.sources.map((s) => (
            <Text key={s}>
              <Text color={accentValue}>•</Text>
              <Text color={colors.text.primary}> {s}</Text>
            </Text>
          ))
        ) : (
          <Text color={colors.text.secondary}>No sources connected</Text>
        )}
      </Box>
    </Box>
  );
}
