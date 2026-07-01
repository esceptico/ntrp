import { expect, test } from "bun:test";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { SwitchControl } from "@/components/ui/SwitchControl";

function mount(): { el: HTMLElement; root: Root; restore: () => void } {
  const el = document.createElement("div");
  document.body.append(el);
  return { el, root: createRoot(el), restore: () => el.remove() };
}
const click = (el: HTMLElement) =>
  el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));

test("SwitchControl renders role=switch with aria-checked + accessible name", () => {
  const on = renderToStaticMarkup(<SwitchControl checked onChange={() => {}} aria-label="Auto-Approve" />);
  expect(on).toContain('role="switch"');
  expect(on).toContain('aria-checked="true"');
  expect(on).toContain('aria-label="Auto-Approve"');
  const off = renderToStaticMarkup(<SwitchControl checked={false} onChange={() => {}} aria-label="Auto-Approve" />);
  expect(off).toContain('aria-checked="false"');
});

test("clicking a switch toggles (onChange with the negated value)", async () => {
  const { el, root, restore } = mount();
  let next: boolean | null = null;
  await act(async () => {
    root.render(<SwitchControl checked={false} onChange={(v) => (next = v)} aria-label="T" />);
  });
  const btn = el.querySelector<HTMLElement>('[role="switch"]')!;
  expect(btn).not.toBeNull();
  await act(async () => click(btn));
  expect(next).toBe(true);
  await act(async () => root.unmount());
  restore();
});

test("a disabled switch does not toggle on click", async () => {
  const { el, root, restore } = mount();
  let next: boolean | null = null;
  await act(async () => {
    root.render(<SwitchControl checked={false} disabled onChange={(v) => (next = v)} aria-label="T" />);
  });
  const btn = el.querySelector<HTMLElement>('[role="switch"]')!;
  await act(async () => click(btn));
  expect(next).toBeNull();
  await act(async () => root.unmount());
  restore();
});

test("both sizes render a switch control", () => {
  for (const size of ["sm", "md"] as const) {
    const html = renderToStaticMarkup(<SwitchControl size={size} checked={false} onChange={() => {}} aria-label={size} />);
    expect(html).toContain('role="switch"');
  }
});
