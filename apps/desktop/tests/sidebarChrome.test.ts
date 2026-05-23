import { expect, test } from "bun:test";

test("sidebar interactive rows opt out of the Electron drag region", async () => {
  const css = await Bun.file(new URL("../src/styles.css", import.meta.url)).text();

  expect(css).toContain(".sidebar {");
  expect(css).toContain("-webkit-app-region: drag;");
  expect(css).toContain(".sidebar [role=\"button\"]");
  expect(css).toContain("-webkit-app-region: no-drag;");
});
