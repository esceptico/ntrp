import { useState, useEffect, useRef, useCallback } from "react";
import { Box, Text } from "ink";
import type { Config } from "../../../types.js";
import { useKeypress, type Key } from "../../../hooks/useKeypress.js";
import {
  getSchedules,
  getScheduleDetail,
  toggleSchedule,
  deleteSchedule,
  type Schedule,
} from "../../../api/client.js";
import { useDimensions } from "../../../contexts/index.js";
import { Panel, Footer, Loading, colors, BaseSelectionList, type RenderItemContext } from "../../ui/index.js";
import { VISIBLE_LINES } from "../../../lib/constants.js";
import { wrapText } from "../../../lib/utils.js";
import { ResultViewer } from "./ResultViewer.js";

interface SchedulesViewerProps {
  config: Config;
  onClose: () => void;
}

function formatRelativeTime(iso: string | null): string {
  if (!iso) return "—";

  const date = new Date(iso);
  const now = new Date();
  const diffMs = date.getTime() - now.getTime();
  const diffHours = diffMs / (1000 * 60 * 60);

  const time = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  if (Math.abs(diffHours) < 24) return `today ${time}`;
  if (diffHours > 0 && diffHours < 48) return `tomorrow ${time}`;
  if (diffHours < 0 && diffHours > -48) return `yesterday ${time}`;

  return `${date.toLocaleDateString([], { month: "short", day: "numeric" })} ${time}`;
}

export function SchedulesViewer({ config, onClose }: SchedulesViewerProps) {
  const { width: terminalWidth } = useDimensions();
  const contentWidth = Math.max(0, terminalWidth - 4);
  const textWidth = contentWidth - 2;

  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [viewingResult, setViewingResult] = useState<{ description: string; result: string } | null>(null);

  const loadedRef = useRef(false);

  const loadSchedules = useCallback(async () => {
    try {
      const data = await getSchedules(config);
      setSchedules(data.schedules);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load schedules");
    } finally {
      setLoading(false);
    }
  }, [config]);

  useEffect(() => {
    if (!loadedRef.current) {
      loadedRef.current = true;
      loadSchedules();
    }
  }, [loadSchedules]);

  const handleToggle = useCallback(async () => {
    const task = schedules[selectedIndex];
    if (!task) return;
    try {
      const result = await toggleSchedule(config, task.task_id);
      setSchedules((prev) =>
        prev.map((s) => (s.task_id === task.task_id ? { ...s, enabled: result.enabled } : s))
      );
    } catch {
      loadSchedules();
    }
  }, [config, schedules, selectedIndex, loadSchedules]);

  const handleDelete = useCallback(async () => {
    const task = schedules[selectedIndex];
    if (!task) return;
    try {
      await deleteSchedule(config, task.task_id);
      setSchedules((prev) => prev.filter((s) => s.task_id !== task.task_id));
      setSelectedIndex((i) => Math.min(i, Math.max(0, schedules.length - 2)));
      setConfirmDelete(false);
    } catch {
      loadSchedules();
      setConfirmDelete(false);
    }
  }, [config, schedules, selectedIndex, loadSchedules]);

  const handleViewResult = useCallback(async () => {
    const task = schedules[selectedIndex];
    if (!task) return;
    try {
      const detail = await getScheduleDetail(config, task.task_id);
      if (detail.last_result) {
        setViewingResult({ description: detail.description, result: detail.last_result });
      }
    } catch {
      // ignore
    }
  }, [config, schedules, selectedIndex]);

  const handleKeypress = useCallback(
    (key: Key) => {
      if (confirmDelete) {
        if (key.name === "y") {
          handleDelete();
        } else {
          setConfirmDelete(false);
        }
        return;
      }

      if (key.name === "escape" || key.name === "q") {
        onClose();
      } else if (key.name === "up" || key.name === "k") {
        setSelectedIndex((i) => Math.max(0, i - 1));
      } else if (key.name === "down" || key.name === "j") {
        setSelectedIndex((i) => Math.min(schedules.length - 1, i + 1));
      } else if (key.name === "space") {
        handleToggle();
      } else if (key.name === "return") {
        handleViewResult();
      } else if (key.name === "d") {
        if (schedules.length > 0) setConfirmDelete(true);
      } else if (key.name === "r") {
        setLoading(true);
        loadSchedules();
      }
    },
    [onClose, schedules.length, handleToggle, confirmDelete, handleDelete, loadSchedules, handleViewResult]
  );

  useKeypress(handleKeypress, { isActive: !viewingResult });

  const renderScheduleItem = useCallback((item: Schedule, { isSelected }: RenderItemContext) => {
    const enabled = item.enabled;
    const statusIcon = enabled ? "✓" : "⏸";
    const statusColor = enabled ? colors.status.success : colors.text.disabled;
    const textColor = isSelected ? colors.text.primary : (enabled ? colors.text.secondary : colors.text.disabled);
    const metaColor = isSelected ? colors.text.secondary : colors.text.muted;

    const nextRun = enabled ? formatRelativeTime(item.next_run_at) : "disabled";
    const lastRun = formatRelativeTime(item.last_run_at);

    return (
      <Box flexDirection="column" marginBottom={1}>
        <Text>
          <Text color={statusColor}>{statusIcon}</Text>
          <Text color={metaColor}>{` ${item.time_of_day}  ${item.recurrence}`}</Text>
        </Text>
        <Text color={textColor}>{wrapText(item.description, textWidth).join('\n')}</Text>
        <Text color={metaColor}>{`next: ${nextRun}   last: ${lastRun}`}</Text>
      </Box>
    );
  }, [textWidth]);

  if (loading) {
    return (
      <Panel title="SCHEDULES" width={contentWidth}>
        <Loading message="Loading schedules..." />
      </Panel>
    );
  }

  if (error) {
    return (
      <Panel title="SCHEDULES" width={contentWidth}>
        <Text color={colors.status.error}>{error}</Text>
        <Footer>q: close</Footer>
      </Panel>
    );
  }

  if (viewingResult) {
    return (
      <ResultViewer
        description={viewingResult.description}
        result={viewingResult.result}
        contentWidth={contentWidth}
        onClose={() => setViewingResult(null)}
      />
    );
  }

  return (
    <Panel title="SCHEDULES" width={contentWidth}>
      <BaseSelectionList<Schedule>
        items={schedules}
        selectedIndex={selectedIndex}
        renderItem={renderScheduleItem}
        visibleLines={VISIBLE_LINES}
        emptyMessage="No scheduled tasks. Use chat to create one."
        getKey={(item) => item.task_id}
        width={contentWidth}
        indicator="▶"
      />

      {confirmDelete && schedules[selectedIndex] && (
        <Box marginTop={1}>
          <Text color={colors.status.warning}>
            Delete "{schedules[selectedIndex].description}"? (y/n)
          </Text>
        </Box>
      )}

      <Footer>
        {confirmDelete
          ? "y: confirm  n: cancel"
          : "enter: view  space: toggle  d: delete  r: refresh  q: close"}
      </Footer>
    </Panel>
  );
}
