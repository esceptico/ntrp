import { expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import { Section } from "@/features/chat/components/ToolViewerSection";

// Regression guard for the tool-info left-clipping bug: the raw-tool <pre> must
// keep wrapping long content. Removing these classes reintroduces the clip.
const WRAP_CLASSES = ["whitespace-pre-wrap", "overflow-wrap:anywhere", "overflow-x-hidden"];

test("Section renders body inside a wrapping <pre> (no horizontal clipping)", () => {
  const body = 'timeout 30s bash -c "sleep 30; code=$?; echo done"';
  const html = renderToStaticMarkup(<Section title="Input" body={body} html="" placeholder="No input." />);
  expect(html).toContain("timeout 30s bash -c"); // quote-free substring (markup escapes ")
  expect(html).toContain("<pre");
  for (const cls of WRAP_CLASSES) expect(html).toContain(cls);
});

test("Section renders highlighted html in a wrapping hljs <pre>", () => {
  const html = renderToStaticMarkup(
    <Section title="Input" body='{"a":1}' html='<span class="hljs-attr">"a"</span>: <span class="hljs-number">1</span>' placeholder="x" />,
  );
  expect(html).toContain("hljs-attr");
  expect(html).toContain('class="hljs'); // highlighted pre keeps the hljs class
  for (const cls of WRAP_CLASSES) expect(html).toContain(cls);
});

test("Section shows the placeholder (no <pre>) when the body is empty", () => {
  const html = renderToStaticMarkup(<Section title="Output" body="" html="" placeholder="Empty result." />);
  expect(html).toContain("Empty result.");
  expect(html).not.toContain("<pre");
});

test("Section exposes a Copy control only when there is a body", () => {
  expect(renderToStaticMarkup(<Section title="Input" body="x" html="" placeholder="p" />)).toContain("Copy");
  expect(renderToStaticMarkup(<Section title="Input" body="" html="" placeholder="p" />)).not.toContain("Copy");
});
