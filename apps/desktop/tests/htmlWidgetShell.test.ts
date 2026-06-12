import { expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

// The shell's CSP is what nested srcdoc widgets inherit — these strings are
// load-bearing security properties, pinned exactly.
const shell = readFileSync(join(import.meta.dir, "../src/public/widget-frame.html"), "utf8");

test("shell CSP allows inline code but keeps the network closed", () => {
  const csp = shell.match(/Content-Security-Policy" content="([^"]+)"/)?.[1] ?? "";
  expect(csp).toContain("default-src 'none'");
  expect(csp).toContain("script-src 'unsafe-inline'");
  expect(csp).toContain("style-src 'unsafe-inline'");
  expect(csp).toContain("img-src data:");
  expect(csp).toContain("form-action 'none'");
  expect(csp).not.toContain("connect-src");
  expect(csp).not.toContain("http");
});

test("shell nests the widget under the exact sandbox", () => {
  expect(shell).toContain('"sandbox", "allow-scripts allow-forms"');
  expect(shell).not.toContain("allow-same-origin");
});

test("shell only accepts ui/init from its parent and announces ui/ready", () => {
  expect(shell).toContain("event.source === window.parent");
  expect(shell).toContain('"ui/ready"');
  expect(shell).toContain('message.method === "ui/init"');
  expect(shell).toContain("event.source === widget.contentWindow");
});
