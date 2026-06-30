import { expect, test } from "bun:test";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { Slider, RangeSlider, valueFromPosition, orderRange } from "@/components/ui/Slider";

function mount(node: React.ReactNode): { el: HTMLElement; root: Root; restore: () => void } {
  const el = document.createElement("div");
  document.body.append(el);
  return { el, root: createRoot(el), restore: () => el.remove() };
}

function fireKey(thumb: HTMLElement, key: string) {
  thumb.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
}

// ── valueFromPosition (pure pointer-drag math) ──────────────────────────────

test("valueFromPosition maps clientX across the track to a clamped, stepped value", () => {
  const rect = { left: 0, width: 100 };
  expect(valueFromPosition(0, rect, 0, 100, 1)).toBe(0); // left edge → min
  expect(valueFromPosition(100, rect, 0, 100, 1)).toBe(100); // right edge → max
  expect(valueFromPosition(50, rect, 0, 100, 1)).toBe(50); // middle
});

test("valueFromPosition clamps out-of-track positions to min/max", () => {
  const rect = { left: 10, width: 100 };
  expect(valueFromPosition(-50, rect, 0, 100, 1)).toBe(0);
  expect(valueFromPosition(9999, rect, 0, 100, 1)).toBe(100);
});

test("valueFromPosition snaps to the step grid", () => {
  const rect = { left: 0, width: 100 };
  // 0..10 step 2 across width 100: 45% → 4.5 raw → snaps to 4.
  expect(valueFromPosition(45, rect, 0, 10, 2)).toBe(4);
  expect(valueFromPosition(55, rect, 0, 10, 2)).toBe(6);
});

test("valueFromPosition is safe for a zero-width track / degenerate range", () => {
  expect(valueFromPosition(50, { left: 0, width: 0 }, 0, 100, 1)).toBe(0);
  expect(valueFromPosition(50, { left: 0, width: 100 }, 5, 5, 1)).toBe(5);
});

// ── render + ARIA ───────────────────────────────────────────────────────────

test("renders role=slider with aria-valuemin/max/now and the accessible name", () => {
  const html = renderToStaticMarkup(
    <Slider value={30} onChange={() => {}} min={0} max={100} step={1} aria-label="Volume" />,
  );
  expect(html).toContain('role="slider"');
  expect(html).toContain('aria-valuemin="0"');
  expect(html).toContain('aria-valuemax="100"');
  expect(html).toContain('aria-valuenow="30"');
  expect(html).toContain('aria-orientation="horizontal"');
  expect(html).toContain('aria-label="Volume"');
});

test("formatValue renders a value readout", () => {
  const html = renderToStaticMarkup(
    <Slider value={42} onChange={() => {}} formatValue={(n) => `${n}%`} aria-label="Opacity" />,
  );
  expect(html).toContain("42%");
});

// ── keyboard stepping ───────────────────────────────────────────────────────

async function withSlider(
  props: { value: number; onChange: (n: number) => void } & Partial<{ min: number; max: number; step: number }>,
  run: (thumb: HTMLElement) => void,
) {
  const { el, root, restore } = mount(null);
  await act(async () => {
    root.render(<Slider aria-label="Test" {...props} />);
  });
  const thumb = el.querySelector<HTMLElement>('[role="slider"]')!;
  expect(thumb).not.toBeNull();
  await act(async () => {
    run(thumb);
  });
  await act(async () => root.unmount());
  restore();
}

test("ArrowRight increments by step", async () => {
  let next: number | null = null;
  await withSlider({ value: 50, onChange: (n) => (next = n), step: 5 }, (thumb) =>
    fireKey(thumb, "ArrowRight"),
  );
  expect(next).toBe(55);
});

test("ArrowRight clamps at max", async () => {
  let next: number | null = null;
  await withSlider({ value: 100, max: 100, onChange: (n) => (next = n) }, (thumb) =>
    fireKey(thumb, "ArrowRight"),
  );
  // Already at max → value doesn't change → onChange not fired.
  expect(next).toBeNull();
});

test("ArrowLeft decrements by step and clamps at min", async () => {
  let next: number | null = null;
  await withSlider({ value: 3, min: 0, onChange: (n) => (next = n), step: 5 }, (thumb) =>
    fireKey(thumb, "ArrowLeft"),
  );
  expect(next).toBe(0); // 3 - 5 = -2 → clamped to 0

  next = null;
  await withSlider({ value: 0, min: 0, onChange: (n) => (next = n) }, (thumb) =>
    fireKey(thumb, "ArrowLeft"),
  );
  expect(next).toBeNull(); // already at min → no change
});

test("Home/End jump to min/max, PageUp/PageDown take larger steps", async () => {
  let next: number | null = null;
  await withSlider({ value: 50, min: 0, max: 100, onChange: (n) => (next = n) }, (thumb) =>
    fireKey(thumb, "Home"),
  );
  expect(next).toBe(0);

  next = null;
  await withSlider({ value: 50, min: 0, max: 100, onChange: (n) => (next = n) }, (thumb) =>
    fireKey(thumb, "End"),
  );
  expect(next).toBe(100);

  next = null;
  await withSlider({ value: 50, min: 0, max: 100, step: 1, onChange: (n) => (next = n) }, (thumb) =>
    fireKey(thumb, "PageUp"),
  );
  expect(next).toBe(60); // pageStep defaults to step * 10
});

// ── RangeSlider ordering (two thumbs can't cross) ───────────────────────────

test("orderRange keeps the two ends ordered and clamped", () => {
  // moving the LOW thumb can't pass the high thumb
  expect(orderRange(0, 80, [20, 60], 0, 100)).toEqual([60, 60]);
  expect(orderRange(0, 40, [20, 60], 0, 100)).toEqual([40, 60]);
  // moving the HIGH thumb can't drop below the low thumb
  expect(orderRange(1, 10, [20, 60], 0, 100)).toEqual([20, 20]);
  expect(orderRange(1, 90, [20, 60], 0, 100)).toEqual([20, 90]);
  // both clamp to [min,max]
  expect(orderRange(0, -5, [20, 60], 0, 100)).toEqual([0, 60]);
  expect(orderRange(1, 999, [20, 60], 0, 100)).toEqual([20, 100]);
});

test("RangeSlider renders two slider thumbs; arrow keys move each, bounded by the other", () => {
  const { el, root, restore } = mount(null);
  let val: [number, number] = [120, 600];
  const onChange = (v: [number, number]) => { val = v; };
  const render = () =>
    act(() => root.render(<RangeSlider value={val} onChange={onChange} min={0} max={1440} step={15} aria-label="Window" />));
  render();
  const thumbs = el.querySelectorAll<HTMLElement>('[role="slider"]');
  expect(thumbs.length).toBe(2);
  expect(thumbs[0].getAttribute("aria-valuenow")).toBe("120");
  expect(thumbs[1].getAttribute("aria-valuenow")).toBe("600");
  // low thumb +step
  fireKey(thumbs[0], "ArrowRight");
  expect(val).toEqual([135, 600]);
  // low thumb can't pass high: jump to End clamps to the high thumb
  render();
  fireKey(el.querySelectorAll<HTMLElement>('[role="slider"]')[0], "End");
  expect(val).toEqual([600, 600]);
  restore();
});
