import { useState, useCallback } from "react";
import { Box, Text } from "ink";
import { useKeypress, type Key } from "../../../hooks/useKeypress.js";
import { Panel, Footer, colors } from "../../ui/index.js";
import { VISIBLE_LINES } from "../../../lib/constants.js";

interface ResultViewerProps {
  description: string;
  result: string;
  contentWidth: number;
  onClose: () => void;
}

export function ResultViewer({ description, result, contentWidth, onClose }: ResultViewerProps) {
  const [scroll, setScroll] = useState(0);

  const lines = result.split("\n");
  const maxScroll = Math.max(0, lines.length - VISIBLE_LINES);

  const handleKeypress = useCallback(
    (key: Key) => {
      if (key.name === "escape" || key.name === "q") {
        onClose();
        return;
      }
      if (key.name === "up" || key.name === "k") {
        setScroll((s) => Math.max(0, s - 1));
      } else if (key.name === "down" || key.name === "j") {
        setScroll((s) => Math.min(maxScroll, s + 1));
      }
    },
    [onClose, maxScroll]
  );

  useKeypress(handleKeypress, { isActive: true });

  const visible = lines.slice(scroll, scroll + VISIBLE_LINES);

  return (
    <Panel title={`RESULT: ${description}`} width={contentWidth}>
      <Text>{visible.join("\n")}</Text>
      {lines.length > VISIBLE_LINES && (
        <Box marginTop={1}>
          <Text color={colors.text.muted}>
            {scroll + 1}-{Math.min(scroll + VISIBLE_LINES, lines.length)} of {lines.length} lines
          </Text>
        </Box>
      )}
      <Footer>j/k: scroll  q: back</Footer>
    </Panel>
  );
}
