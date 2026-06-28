import { expect, test } from "bun:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Tab, Tabs } from "@/components/ui/Tabs";
import { SLIDE_PAGE_VARIANTS } from "@/components/ui/TabPanels";

test("renders a button per tab and marks the active one", () => {
  const html = renderToStaticMarkup(
    <Tabs value="b" onChange={() => {}} variant="underline">
      <Tab value="a">Alpha</Tab>
      <Tab value="b">Beta</Tab>
    </Tabs>,
  );
  expect(html).toContain("Alpha");
  expect(html).toContain("Beta");
  expect(html).toContain('role="tablist"');
  expect((html.match(/role="tab"/g) ?? []).length).toBe(2);
  expect(html).toContain('aria-selected="true"');
});

test("underline variant renders exactly one underline indicator", () => {
  const html = renderToStaticMarkup(
    <Tabs value="a" onChange={() => {}} variant="underline">
      <Tab value="a">Alpha</Tab>
      <Tab value="b">Beta</Tab>
    </Tabs>,
  );
  expect((html.match(/data-tab-indicator/g) ?? []).length).toBe(1);
  expect(html).toContain('data-tab-indicator="underline"');
});

test("pill variant renders a pill indicator with the supplied indicator class", () => {
  const html = renderToStaticMarkup(
    <Tabs
      value="a"
      onChange={() => {}}
      variant="pill"
      indicatorClassName="indicator-probe"
    >
      <Tab value="a">Alpha</Tab>
    </Tabs>,
  );
  expect(html).toContain('data-tab-indicator="pill"');
  expect(html).toContain("indicator-probe");
});

test("page panel variant matches settings-style directional swaps", () => {
  expect(SLIDE_PAGE_VARIANTS.exit(-1)).toMatchObject({ x: 16 });
  expect(SLIDE_PAGE_VARIANTS.enter(-1)).toMatchObject({ x: -16 });
  expect(SLIDE_PAGE_VARIANTS.exit(1)).toMatchObject({ x: -16 });
  expect(SLIDE_PAGE_VARIANTS.enter(1)).toMatchObject({ x: 16 });
});
