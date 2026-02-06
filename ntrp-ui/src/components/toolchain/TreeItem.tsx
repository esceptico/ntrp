import React from "react";
import { Box, Text } from "ink";
import { colors } from "../ui/colors.js";
import { useAccentColor } from "../../hooks/index.js";
import { truncateText } from "../../lib/utils.js";
import { BULLET, MAX_TOOL_RESULT_LINE_CHARS } from "../../lib/constants.js";
import { DiffDisplay } from "./DiffDisplay.js";
import type { ToolChainItem } from "./types.js";

interface TreeNode extends ToolChainItem {
  children: TreeNode[];
}

function getStatusColor(status: ToolChainItem["status"], accentValue: string): string {
  switch (status) {
    case "error":
      return colors.status.error;
    case "running":
    case "done":
      return accentValue;
    case "pending":
      return colors.text.muted;
    default: {
      const _exhaustive: never = status;
      return _exhaustive;
    }
  }
}

function isContainer(name: string): boolean {
  return name === "delegate" || name === "explore";
}

export function buildTree(items: ToolChainItem[]): TreeNode[] {
  const nodeMap = new Map<string, TreeNode>();
  for (const item of items) {
    nodeMap.set(item.id, { ...item, children: [] });
  }

  const roots: TreeNode[] = [];
  for (const item of items) {
    const node = nodeMap.get(item.id)!;
    if (item.parentId && nodeMap.has(item.parentId)) {
      nodeMap.get(item.parentId)!.children.push(node);
    } else {
      roots.push(node);
    }
  }

  const sortBySeq = (a: TreeNode, b: TreeNode) => (a.seq ?? 0) - (b.seq ?? 0);
  roots.sort(sortBySeq);
  for (const node of nodeMap.values()) {
    node.children.sort(sortBySeq);
  }
  return roots;
}

interface TreeItemProps {
  node: TreeNode;
  indent: number;
  expanded: boolean;
  width: number;
}

export function TreeItem({ node, indent, expanded, width }: TreeItemProps) {
  const { accentValue } = useAccentColor();
  const color = getStatusColor(node.status, accentValue);
  const icon = `${BULLET} `;
  const label = node.description || node.name;
  const prefix = indent > 0 ? "  ".repeat(indent) : "";
  const contentWidth = Math.max(0, width - prefix.length - 4);

  if (!isContainer(node.name)) {
    const preview = node.preview || node.result?.split("\n")[0] || "";
    const resultLine = truncateText(preview, Math.min(MAX_TOOL_RESULT_LINE_CHARS, contentWidth - 2));
    const hasDiff = node.metadata?.diff && node.status === "done";

    return (
      <Box flexDirection="column" width={width} overflow="hidden">
        <Text>
          <Text color={color}>{prefix}{icon}</Text>
          <Text>{truncateText(label, contentWidth)}</Text>
        </Text>
        {resultLine && node.status === "done" && !hasDiff && (
          <Text color={colors.text.secondary}>{prefix}⎿ {resultLine}</Text>
        )}
        {hasDiff && <DiffDisplay diff={node.metadata!.diff!} prefix={prefix} width={width - prefix.length} />}
      </Box>
    );
  }

  const toolCount = node.children.length;
  const stats = toolCount > 0 ? ` · ${toolCount} tool${toolCount !== 1 ? "s" : ""}` : "";
  const current = node.children.find((c) => c.status === "running") || node.children[node.children.length - 1];
  const currentLabel = current && !isContainer(current.name) ? current.description || current.name : null;

  if (!expanded) {
    return (
      <Box flexDirection="column" width={width} overflow="hidden">
        <Text>
          <Text color={color}>{prefix}{icon}</Text>
          <Text>{truncateText(label, contentWidth - 15)}</Text>
          {stats && <Text color={colors.text.muted}>{stats}</Text>}
        </Text>
        {currentLabel && (
          <Text color={colors.text.secondary}>{prefix}⎿ – {truncateText(currentLabel, contentWidth - 4)}</Text>
        )}
        {node.children.filter((c) => isContainer(c.name)).map((child) => (
          <TreeItem key={child.id} node={child} indent={indent + 1} expanded={false} width={width} />
        ))}
      </Box>
    );
  }

  return (
    <Box flexDirection="column" width={width} overflow="hidden">
      <Text>
        <Text color={color}>{prefix}{icon}</Text>
        <Text>{truncateText(label, contentWidth - 15)}</Text>
        {stats && <Text color={colors.text.muted}>{stats}</Text>}
      </Text>
      {node.children.map((child) => (
        <TreeItem key={child.id} node={child} indent={indent + 1} expanded={true} width={width} />
      ))}
    </Box>
  );
}
