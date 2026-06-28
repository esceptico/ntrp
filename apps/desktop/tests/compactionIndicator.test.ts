import { expect, test } from "bun:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import {
  CompactionIndicator,
  CompactionIndicatorContent,
} from "@/components/CompactionIndicator";
import { setState } from "@/store/index";

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
