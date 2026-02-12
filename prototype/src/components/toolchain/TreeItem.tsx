import { colors } from "../ui/colors.js";
import { truncateText } from "../../lib/utils.js";
import { MAX_TOOL_RESULT_LINE_CHARS } from "../../lib/constants.js";
import { StructuredDiffDisplay } from "./DiffDisplay.js";
import type { ToolChainItem } from "./types.js";

const TOOL_MARKER = "\u2192"; // →

interface TreeNode extends ToolChainItem {
  children: TreeNode[];
}

function getStatusColor(status: ToolChainItem["status"]): string {
  switch (status) {
    case "error":
      return colors.text.muted;
    case "running":
      return colors.text.secondary;
    case "done":
      return colors.text.disabled;
    case "pending":
      return colors.text.disabled;
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
  const color = getStatusColor(node.status);
  const icon = `${TOOL_MARKER} `;
  const label = node.description || node.name;
  const prefix = indent > 0 ? "  ".repeat(indent) : "";
  const contentWidth = Math.max(0, width - prefix.length - 2);

  if (!isContainer(node.name)) {
    const preview = node.preview || node.result?.split("\n")[0] || "";
    const resultLine = truncateText(preview, Math.min(MAX_TOOL_RESULT_LINE_CHARS, contentWidth - 2));
    const diff = node.data?.diff as { path: string; before: string; after: string } | undefined;
    const hasDiff = diff && node.status === "done";

    return (
      <box flexDirection="column" width={width} overflow="hidden">
        <text>
          <span fg={color}>{prefix}{icon}</span>
          <span fg={colors.text.secondary}>{truncateText(label, contentWidth)}</span>
        </text>
        {resultLine && node.status === "done" && !hasDiff && (
          <text>
            <span fg={colors.text.muted}>{prefix}⎿ {resultLine}</span>
          </text>
        )}
        {hasDiff && <StructuredDiffDisplay before={diff.before} after={diff.after} path={diff.path} prefix={prefix} width={width - prefix.length} />}
      </box>
    );
  }

  const toolCount = node.children.length;
  const stats = toolCount > 0 ? ` · ${toolCount} tool${toolCount !== 1 ? "s" : ""}` : "";
  const current = node.children.find((c) => c.status === "running") || node.children[node.children.length - 1];
  const currentLabel = current && !isContainer(current.name) ? current.description || current.name : null;

  if (!expanded) {
    return (
      <box flexDirection="column" width={width} overflow="hidden">
        <text>
          <span fg={color}>{prefix}{icon}</span>
          <span fg={colors.text.secondary}>{truncateText(label, contentWidth - 15)}</span>
          {stats && <span fg={colors.text.muted}>{stats}</span>}
        </text>
        {currentLabel && (
          <text>
            <span fg={colors.text.muted}>{prefix}⎿ – {truncateText(currentLabel, contentWidth - 4)}</span>
          </text>
        )}
        {node.children.filter((c) => isContainer(c.name)).map((child) => (
          <TreeItem key={child.id} node={child} indent={indent + 1} expanded={false} width={width} />
        ))}
      </box>
    );
  }

  return (
    <box flexDirection="column" width={width} overflow="hidden">
      <text>
        <span fg={color}>{prefix}{icon}</span>
        <span fg={colors.text.secondary}>{truncateText(label, contentWidth - 15)}</span>
        {stats && <span fg={colors.text.muted}>{stats}</span>}
      </text>
      {node.children.map((child) => (
        <TreeItem key={child.id} node={child} indent={indent + 1} expanded={true} width={width} />
      ))}
    </box>
  );
}
