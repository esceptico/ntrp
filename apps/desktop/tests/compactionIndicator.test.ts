import { expect, test } from "bun:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  CompactionIndicator,
  CompactionIndicatorContent,
} from "../src/components/CompactionIndicator.tsx";
import { setState } from "../src/store/index.ts";

test("compaction indicator does not render a finished compaction toast", () => {
  setState({ compacting: false });

  expect(renderToStaticMarkup(createElement(CompactionIndicator))).not.toContain(
    "Conversation compacted",
  );
});

test("compaction indicator renders the live spinner state", () => {
  expect(
    renderToStaticMarkup(createElement(CompactionIndicatorContent, { compacting: true })),
  ).toContain("Compacting conversation");
});
