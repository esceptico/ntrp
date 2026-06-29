import { expect, test } from "bun:test";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { RadioGroup, RadioGroupItem } from "@/components/ui/RadioGroup";

function setupDom(): { rootEl: HTMLElement; root: Root; restore: () => void } {
  const rootEl = document.createElement("div");
  document.body.append(rootEl);
  return {
    rootEl,
    root: createRoot(rootEl),
    restore: () => rootEl.remove(),
  };
}

function group(value: string, onChange: (v: string) => void) {
  return (
    <RadioGroup value={value} onChange={onChange} aria-label="Density">
      <RadioGroupItem index={0} value="comfortable" label="Comfortable" description="More air" />
      <RadioGroupItem index={1} value="cozy" label="Cozy" />
      <RadioGroupItem index={2} value="compact" label="Compact" />
    </RadioGroup>
  );
}

test("renders a radiogroup with a radio per item and the checked one marked", async () => {
  const { rootEl, root, restore } = setupDom();
  await act(async () => {
    root.render(group("cozy", () => {}));
  });

  const groupEl = rootEl.querySelector('[role="radiogroup"]');
  expect(groupEl).not.toBeNull();
  expect(groupEl?.getAttribute("aria-label")).toBe("Density");

  const radios = rootEl.querySelectorAll<HTMLElement>('[role="radio"]');
  expect(radios.length).toBe(3);
  expect(radios[1].getAttribute("aria-checked")).toBe("true");
  expect(radios[0].getAttribute("aria-checked")).toBe("false");
  expect(rootEl.textContent).toContain("Comfortable");
  expect(rootEl.textContent).toContain("More air");

  // Roving tabIndex: only the checked row is tabbable.
  expect(radios[1].getAttribute("tabindex")).toBe("0");
  expect(radios[0].getAttribute("tabindex")).toBe("-1");
  expect(radios[2].getAttribute("tabindex")).toBe("-1");

  await act(async () => root.unmount());
  restore();
});

test("clicking a row calls onChange with that row's value", async () => {
  const { rootEl, root, restore } = setupDom();
  const calls: string[] = [];
  await act(async () => {
    root.render(group("comfortable", (v) => calls.push(v)));
  });

  const radios = rootEl.querySelectorAll<HTMLElement>('[role="radio"]');
  await act(async () => {
    radios[2].click();
  });

  expect(calls).toEqual(["compact"]);

  await act(async () => root.unmount());
  restore();
});

test("ArrowDown moves focus to the next row and auto-selects it", async () => {
  const { rootEl, root, restore } = setupDom();
  const calls: string[] = [];
  await act(async () => {
    root.render(group("comfortable", (v) => calls.push(v)));
  });

  const radios = rootEl.querySelectorAll<HTMLElement>('[role="radio"]');
  await act(async () => {
    radios[0].focus();
    radios[0].dispatchEvent(
      new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }),
    );
  });

  // Auto-activation: ArrowDown both moved focus and selected the next value.
  expect(calls).toEqual(["cozy"]);
  expect(document.activeElement).toBe(radios[1]);

  await act(async () => root.unmount());
  restore();
});
