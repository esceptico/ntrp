import { useMemo, useState, useCallback } from "react";
import { useDimensions } from "../contexts/index.js";
import { useKeypress, type Key } from "../hooks/index.js";
import { TreeItem, buildTree, type ToolChainItem } from "./toolchain/index.js";

export type { ToolChainItem } from "./toolchain/index.js";

export function ToolChainDisplay({ items, maxItems = 5 }: { items: ToolChainItem[]; maxItems?: number }) {
  const { width } = useDimensions();
  const [expanded, setExpanded] = useState(false);

  useKeypress(
    useCallback((key: Key) => {
      if (key.ctrl && key.name === "o") setExpanded((prev) => !prev);
    }, []),
    { isActive: true }
  );

  const roots = useMemo(() => {
    return buildTree(items).slice(-maxItems);
  }, [items, maxItems]);

  if (roots.length === 0) return null;

  return (
    <box flexDirection="column" overflow="hidden" paddingLeft={3}>
      {roots.map((node) => (
        <TreeItem key={node.id} node={node} indent={0} expanded={expanded} width={width - 3} />
      ))}
    </box>
  );
}
