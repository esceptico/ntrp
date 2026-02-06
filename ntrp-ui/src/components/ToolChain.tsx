import React, { useMemo, useState } from "react";
import { Box } from "ink";
import { useDimensions } from "../contexts/index.js";
import { useKeypress, type Key } from "../hooks/index.js";
import { TreeItem, buildTree, type ToolChainItem } from "./toolchain/index.js";

export type { ToolChainItem } from "./toolchain/index.js";

export function ToolChainDisplay({ items, maxItems = 5 }: { items: ToolChainItem[]; maxItems?: number }) {
  const { width: terminalWidth } = useDimensions();
  const [expanded, setExpanded] = useState(false);

  useKeypress(
    React.useCallback((key: Key) => {
      if (key.ctrl && key.name === "o") setExpanded((prev) => !prev);
    }, []),
    { isActive: true }
  );

  const roots = useMemo(() => {
    return buildTree(items).slice(-maxItems);
  }, [items, maxItems]);

  if (roots.length === 0) return null;

  return (
    <Box flexDirection="column" width={terminalWidth} overflow="hidden">
      {roots.map((node) => (
        <TreeItem key={node.id} node={node} indent={0} expanded={expanded} width={terminalWidth - 2} />
      ))}
    </Box>
  );
}
