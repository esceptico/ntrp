import { expect, test } from "bun:test";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { Select, type SelectOption } from "@/components/ui/Select";

// AnchoredPopover (which Select reuses for the portal) renders into `#app`, so
// the harness must provide both the render root and `#app`.
function setupDom(): { rootEl: HTMLElement; appEl: HTMLElement; root: Root; restore: () => void } {
  const rootEl = document.createElement("div");
  rootEl.id = "root";
  const appEl = document.createElement("div");
  appEl.id = "app";
  document.body.append(rootEl, appEl);
  return {
    rootEl,
    appEl,
    root: createRoot(rootEl),
    restore: () => {
      rootEl.remove();
      appEl.remove();
    },
  };
}

const OPTIONS: SelectOption[] = [
  { value: "fact", label: "Facts", description: "Stable knowledge" },
  { value: "directive", label: "Rules" },
  { value: "source", label: "Sources" },
];

function select(value: string, onChange: (v: string) => void) {
  return <Select value={value} onChange={onChange} options={OPTIONS} aria-label="Kind" />;
}

test("renders a combobox trigger showing the selected option's label", async () => {
  const { rootEl, root, restore } = setupDom();
  await act(async () => {
    root.render(select("directive", () => {}));
  });

  const trigger = rootEl.querySelector<HTMLElement>('[role="combobox"]');
  expect(trigger).not.toBeNull();
  expect(trigger?.getAttribute("aria-haspopup")).toBe("listbox");
  expect(trigger?.getAttribute("aria-expanded")).toBe("false");
  expect(trigger?.getAttribute("aria-label")).toBe("Kind");
  expect(trigger?.textContent).toContain("Rules");

  // Closed: no listbox is portaled yet.
  expect(document.querySelector('[role="listbox"]')).toBeNull();

  await act(async () => root.unmount());
  restore();
});

test("opening shows a listbox with an option per choice, the selected one marked", async () => {
  const { rootEl, root, restore } = setupDom();
  await act(async () => {
    root.render(select("source", () => {}));
  });

  const trigger = rootEl.querySelector<HTMLElement>('[role="combobox"]')!;
  await act(async () => {
    trigger.click();
  });

  expect(trigger.getAttribute("aria-expanded")).toBe("true");

  const listbox = document.querySelector('[role="listbox"]');
  expect(listbox).not.toBeNull();

  const optionEls = document.querySelectorAll<HTMLElement>('[role="option"]');
  expect(optionEls.length).toBe(3);
  expect(optionEls[0].textContent).toContain("Facts");
  expect(optionEls[0].textContent).toContain("Stable knowledge");

  // aria-selected + roving tabindex track the current value (third option).
  expect(optionEls[2].getAttribute("aria-selected")).toBe("true");
  expect(optionEls[0].getAttribute("aria-selected")).toBe("false");
  expect(optionEls[2].getAttribute("tabindex")).toBe("0");
  expect(optionEls[0].getAttribute("tabindex")).toBe("-1");

  await act(async () => root.unmount());
  restore();
});

test("clicking an option calls onChange with its value and closes the listbox", async () => {
  const { rootEl, root, restore } = setupDom();
  const calls: string[] = [];
  await act(async () => {
    root.render(select("fact", (v) => calls.push(v)));
  });

  const trigger = rootEl.querySelector<HTMLElement>('[role="combobox"]')!;
  await act(async () => {
    trigger.click();
  });

  const optionEls = document.querySelectorAll<HTMLElement>('[role="option"]');
  await act(async () => {
    optionEls[1].click();
  });

  expect(calls).toEqual(["directive"]);
  // Closed again: the trigger reports the collapsed state. (The portaled panel
  // lingers briefly while AnimatePresence runs its exit tween, so we assert on
  // the authoritative open-state flag rather than racing the unmount.)
  expect(trigger.getAttribute("aria-expanded")).toBe("false");

  await act(async () => root.unmount());
  restore();
});
