// Register additional tree-sitter parsers and update markdown injection mapping.
// addDefaultParsers is exported at runtime but missing from @opentui/core type defs.

import { resolve } from "path";
import { existsSync } from "fs";

// @ts-ignore — runtime export, not typed
import { addDefaultParsers } from "@opentui/core";

// Find node_modules — works from both src/lib/ (dev) and dist/ (build)
function findNodeModules(): string {
  let dir = import.meta.dir;
  for (let i = 0; i < 5; i++) {
    const candidate = resolve(dir, "node_modules");
    if (existsSync(candidate)) return candidate;
    dir = resolve(dir, "..");
  }
  throw new Error("Could not find node_modules");
}

function pkg(nm: string, name: string) {
  return {
    wasm: resolve(nm, `tree-sitter-${name}/tree-sitter-${name}.wasm`),
    highlights: resolve(nm, `tree-sitter-${name}/queries/highlights.scm`),
  };
}

try {
  const nm = findNodeModules();
  const python = pkg(nm, "python");
  const bash = pkg(nm, "bash");
  const json = pkg(nm, "json");
  const mdAssets = resolve(nm, "@opentui/core/assets/markdown");

  addDefaultParsers([
    { filetype: "python", queries: { highlights: [python.highlights] }, wasm: python.wasm },
    { filetype: "bash", queries: { highlights: [bash.highlights] }, wasm: bash.wasm },
    { filetype: "json", queries: { highlights: [json.highlights] }, wasm: json.wasm },
    {
      filetype: "markdown",
      queries: {
        highlights: [resolve(mdAssets, "highlights.scm")],
        injections: [resolve(mdAssets, "injections.scm")],
      },
      wasm: resolve(mdAssets, "tree-sitter-markdown.wasm"),
      injectionMapping: {
        nodeTypes: { inline: "markdown_inline", pipe_table_cell: "markdown_inline" },
        infoStringMap: {
          javascript: "javascript",
          js: "javascript",
          typescript: "typescript",
          ts: "typescript",
          markdown: "markdown",
          md: "markdown",
          python: "python",
          py: "python",
          bash: "bash",
          sh: "bash",
          shell: "bash",
          zsh: "bash",
          json: "json",
          jsonc: "json",
        },
      },
    },
  ]);
} catch {
  // non-fatal — syntax highlighting for extra languages unavailable
}
