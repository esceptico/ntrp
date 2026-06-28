import type { MemoryArtifact } from "@/api/memoryArtifacts";

export type TreeNode = {
  name: string;
  path: string;
  kind: "directory" | "file";
  artifact?: MemoryArtifact;
  children: TreeNode[];
};

// Folder sort + default-expand order, post topics/-unification (entities/ & projects/
// are folded into topics/).
const DIRECTORY_ORDER = ["topics", "daily", "insights", "observations", "context", "facts", "changelog"];
const DEFAULT_EXPANDED_DIRS = new Set(["topics", "daily", "insights", "observations"]);

function directorySort(a: TreeNode, b: TreeNode) {
  if (a.kind !== b.kind) return a.kind === "directory" ? -1 : 1;
  const ai = DIRECTORY_ORDER.indexOf(a.name);
  const bi = DIRECTORY_ORDER.indexOf(b.name);
  return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi) || a.name.localeCompare(b.name);
}

function addNode(parent: TreeNode, parts: string[], artifact: MemoryArtifact, pathPrefix = "") {
  const [part, ...rest] = parts;
  if (!part) return;
  const nodePath = pathPrefix ? `${pathPrefix}/${part}` : part;
  if (rest.length === 0) {
    parent.children.push({ name: part, path: artifact.path, kind: "file", artifact, children: [] });
    return;
  }
  let child = parent.children.find((n) => n.kind === "directory" && n.name === part);
  if (!child) {
    child = { name: part, path: nodePath, kind: "directory", children: [] };
    parent.children.push(child);
  }
  addNode(child, rest, artifact, nodePath);
}

export function buildArtifactTree(artifacts: MemoryArtifact[]) {
  const root: TreeNode = { name: "root", path: "", kind: "directory", children: [] };
  for (const artifact of artifacts) {
    // Root files (me.md, index.md, …) live AT the vault root — render them at the top
    // level alongside the real folders (daily/, topics/, …), not under a fake "memory" dir.
    addNode(root, artifact.path.split("/"), artifact);
  }
  const sortRec = (node: TreeNode) => {
    node.children.sort(directorySort);
    node.children.forEach(sortRec);
  };
  sortRec(root);
  return root.children;
}

export function collectDefaultFolderPaths(nodes: TreeNode[]): string[] {
  const out: string[] = [];
  const walk = (ns: TreeNode[]) => {
    for (const n of ns) {
      if (n.kind === "directory") {
        if (DEFAULT_EXPANDED_DIRS.has(n.path)) out.push(n.path);
        walk(n.children);
      }
    }
  };
  walk(nodes);
  return out;
}

export function countFiles(node: TreeNode): number {
  if (node.kind === "file") return 1;
  return node.children.reduce((sum, child) => sum + countFiles(child), 0);
}

/** File-leaf paths in the order the tree renders them (depth-first, already
 *  directory-sorted). Drives the detail-pane slide direction so it matches the
 *  visible list position — selecting a note further down slides in from the
 *  right, further up from the left. */
export function flattenTreeFiles(nodes: TreeNode[]): string[] {
  const out: string[] = [];
  const walk = (ns: TreeNode[]) => {
    for (const n of ns) {
      if (n.kind === "file") out.push(n.path);
      else walk(n.children);
    }
  };
  walk(nodes);
  return out;
}
