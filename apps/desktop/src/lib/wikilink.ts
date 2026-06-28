import { createContext } from "react";
import { visit } from "unist-util-visit";
import type { Root, Text } from "mdast";

// Obsidian-style [[Subject]] wikilinks for memory notes. The matched target
// becomes a `link` mdast node carrying className + data-wikilink, so it renders
// as an <a> that the Markdown Anchor intercepts (no browser nav).
const WIKILINK_RE = /\[\[([^[\]]+)\]\]/g;

/** remark plugin: split `text` nodes on [[Subject]] and inject inert links. */
export function remarkWikiLink() {
  return (tree: Root) => {
    visit(tree, "text", (node: Text, index, parent) => {
      if (!parent || index == null || !node.value.includes("[[")) return;
      const parts: Array<Text | WikiLinkNode> = [];
      let last = 0;
      WIKILINK_RE.lastIndex = 0;
      let m: RegExpExecArray | null;
      while ((m = WIKILINK_RE.exec(node.value))) {
        if (m.index > last) parts.push({ type: "text", value: node.value.slice(last, m.index) });
        const target = m[1].trim();
        parts.push({
          type: "link",
          url: "#wikilink",
          data: { hProperties: { className: "wikilink", "data-wikilink": target } },
          children: [{ type: "text", value: target }],
        });
        last = m.index + m[0].length;
      }
      if (parts.length === 0) return;
      if (last < node.value.length) parts.push({ type: "text", value: node.value.slice(last) });
      parent.children.splice(index, 1, ...parts);
      return index + parts.length;
    });
  };
}

type WikiLinkNode = {
  type: "link";
  url: string;
  data: { hProperties: { className: string; "data-wikilink": string } };
  children: Text[];
};

/** Mirror of the server's `_slug` (memory/artifacts.py): lowercase, collapse
 *  runs of non-[A-Za-z0-9._-] to "-", strip leading/trailing .-_ , cap 60. */
export function wikiSlug(s: string): string {
  const base = s
    .trim()
    .replace(/[^A-Za-z0-9._-]+/g, "-")
    .replace(/^[.\-_]+|[.\-_]+$/g, "")
    .toLowerCase()
    .slice(0, 60)
    .replace(/^[.\-_]+|[.\-_]+$/g, "");
  return base || "entity";
}

export type WikiLinkHandlers = {
  /** Navigate to the target subject page. */
  onNavigate: (target: string) => void;
  /** Whether a target resolves to an existing note (drives Obsidian-style
   *  muted "unresolved" rendering for dangling links). */
  exists: (target: string) => boolean;
};

/** Resolution handlers for [[Subject]] clicks. Default undefined so wikilinks
 *  are inert styled text everywhere except the memory view. */
export const WikiLinkContext = createContext<WikiLinkHandlers | undefined>(undefined);
