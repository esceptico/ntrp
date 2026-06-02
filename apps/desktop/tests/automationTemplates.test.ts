import { expect, test } from "bun:test";

test("templates do not use keyword-signal suggestions", async () => {
  const source = await Bun.file(
    new URL("../src/components/automations/templates.ts", import.meta.url),
  ).text();

  expect(source).not.toContain("TEMPLATE_SIGNALS");
  expect(source).not.toContain("suggestTemplatesForContext");
  expect(source).not.toContain("RegExp");
});
