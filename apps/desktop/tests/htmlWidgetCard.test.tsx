import { afterEach, beforeEach, expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import { JSDOM } from "jsdom";
import { HtmlWidgetCard } from "@/features/chat/components/HtmlWidgetCard";
import type { ActivityItem } from "@/stores/index";

const originalWindow = globalThis.window;
const originalDocument = globalThis.document;
const originalGetComputedStyle = globalThis.getComputedStyle;

beforeEach(() => {
  const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost" });
  globalThis.window = dom.window as unknown as Window & typeof globalThis;
  globalThis.document = dom.window.document;
  globalThis.getComputedStyle = dom.window.getComputedStyle.bind(
    dom.window,
  ) as typeof globalThis.getComputedStyle;
});

afterEach(() => {
  globalThis.window = originalWindow;
  globalThis.document = originalDocument;
  globalThis.getComputedStyle = originalGetComputedStyle;
});

function widgetItem(overrides: Partial<ActivityItem>): ActivityItem {
  return {
    id: "t1",
    kind: "render_html",
    semanticKind: "html_widget",
    target: "render_html",
    htmlWidget: { html: "<form>pick</form>", title: "Pick a time slot", mode: "input" },
    ...overrides,
  };
}

test("pending input card shows Awaiting input badge, Decline button, and the exact sandbox", () => {
  const markup = renderToStaticMarkup(<HtmlWidgetCard item={widgetItem({ status: "ongoing" })} />);

  expect(markup).toContain("Awaiting input");
  expect(markup).toContain("Decline");
  expect(markup).toContain('sandbox="allow-scripts allow-forms"');
  expect(markup).not.toContain("allow-same-origin");
  expect(markup).not.toContain("pointer-events-none");
});

test("iframe loads the widget-frame shell instead of inlining the model HTML", () => {
  const markup = renderToStaticMarkup(<HtmlWidgetCard item={widgetItem({ status: "ongoing" })} />);

  // srcdoc would inherit the app's strict CSP and kill the widget's inline
  // scripts — the model HTML must travel via ui/init postMessage, never markup.
  expect(markup).toContain('src="widget-frame.html"');
  expect(markup).not.toContain("srcdoc");
  expect(markup).not.toContain("<form>pick</form>");
});

test("accepted input card freezes with a Submitted badge", () => {
  const markup = renderToStaticMarkup(
    <HtmlWidgetCard
      item={widgetItem({ status: "executed", result: '{"action": "accept", "values": {"rating": 4}}' })}
    />,
  );

  expect(markup).toContain("Submitted");
  expect(markup).toContain("pointer-events-none");
  expect(markup).not.toContain("Awaiting input");
  expect(markup).not.toContain("Decline</button>");
});

test("declined and dismissed envelopes map to their badges", () => {
  const declined = renderToStaticMarkup(
    <HtmlWidgetCard
      item={widgetItem({ status: "executed", result: '{"action": "decline", "values": {}}' })}
    />,
  );
  expect(declined).toContain("Declined");
  expect(declined).toContain("pointer-events-none");

  const dismissed = renderToStaticMarkup(
    <HtmlWidgetCard
      item={widgetItem({ status: "executed", result: '{"action": "cancel", "values": {}}' })}
    />,
  );
  expect(dismissed).toContain("Dismissed");
  expect(dismissed).toContain("pointer-events-none");
});

test("display-mode card never freezes", () => {
  const markup = renderToStaticMarkup(
    <HtmlWidgetCard
      item={widgetItem({
        status: "executed",
        result: 'Rendered HTML widget "Quarterly burn".',
        htmlWidget: { html: "<div>chart</div>", title: "Quarterly burn", mode: "display" },
      })}
    />,
  );

  expect(markup).toContain("Quarterly burn");
  expect(markup).not.toContain("pointer-events-none");
  expect(markup).not.toContain("opacity-60");
  expect(markup).not.toContain("Awaiting input");
});
