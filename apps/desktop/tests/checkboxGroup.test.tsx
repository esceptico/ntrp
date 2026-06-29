import { expect, test } from "bun:test";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { CheckboxGroup, CheckboxGroupItem } from "@/components/ui/CheckboxGroup";

function setupDom(): { host: HTMLElement; root: Root; restore: () => void } {
  const host = document.createElement("div");
  document.body.append(host);
  return {
    host,
    root: createRoot(host),
    restore: () => host.remove(),
  };
}

function Group({
  value,
  onChange,
}: {
  value: string[];
  onChange: (next: string[]) => void;
}) {
  return (
    <CheckboxGroup value={value} onChange={onChange} aria-label="Toppings">
      <CheckboxGroupItem value="a" label="Anchovies" />
      <CheckboxGroupItem value="b" label="Basil" description="fresh" />
      <CheckboxGroupItem value="c" label="Cheese" />
    </CheckboxGroup>
  );
}

async function settle() {
  await act(async () => {
    await new Promise((r) => setTimeout(r, 5));
  });
}

test("renders role=group with an item per child and reflects aria-checked", async () => {
  const { host, root, restore } = setupDom();
  await act(async () => {
    root.render(<Group value={["b"]} onChange={() => {}} />);
  });
  await settle();

  const group = host.querySelector('[role="group"]');
  expect(group).not.toBeNull();
  expect(group?.getAttribute("aria-label")).toBe("Toppings");

  const boxes = host.querySelectorAll<HTMLElement>('[role="checkbox"]');
  expect(boxes.length).toBe(3);
  // Only the checked value reports aria-checked="true".
  expect(boxes[0].getAttribute("aria-checked")).toBe("false");
  expect(boxes[1].getAttribute("aria-checked")).toBe("true");
  expect(boxes[2].getAttribute("aria-checked")).toBe("false");
  // Each row exposes its label as an accessible name.
  expect(boxes[0].getAttribute("aria-label")).toBe("Anchovies");

  await act(async () => root.unmount());
  restore();
});

test("clicking a row calls onChange adding its value to the array", async () => {
  const { host, root, restore } = setupDom();
  let received: string[] | null = null;
  await act(async () => {
    root.render(<Group value={["a"]} onChange={(next) => (received = next)} />);
  });
  await settle();

  const boxes = host.querySelectorAll<HTMLElement>('[role="checkbox"]');
  // Toggle the third row on.
  await act(async () => {
    boxes[2].click();
  });
  expect(received).toEqual(["a", "c"]);

  await act(async () => root.unmount());
  restore();
});

test("clicking a checked row removes its value from the array", async () => {
  const { host, root, restore } = setupDom();
  let received: string[] | null = null;
  await act(async () => {
    root.render(<Group value={["a", "b"]} onChange={(next) => (received = next)} />);
  });
  await settle();

  const boxes = host.querySelectorAll<HTMLElement>('[role="checkbox"]');
  // Untoggle the first (checked) row.
  await act(async () => {
    boxes[0].click();
  });
  expect(received).toEqual(["b"]);

  await act(async () => root.unmount());
  restore();
});

test("Space toggles the focused row", async () => {
  const { host, root, restore } = setupDom();
  let received: string[] | null = null;
  await act(async () => {
    root.render(<Group value={[]} onChange={(next) => (received = next)} />);
  });
  await settle();

  const boxes = host.querySelectorAll<HTMLElement>('[role="checkbox"]');
  await act(async () => {
    boxes[1].dispatchEvent(
      new KeyboardEvent("keydown", { key: " ", bubbles: true, cancelable: true }),
    );
  });
  expect(received).toEqual(["b"]);

  await act(async () => root.unmount());
  restore();
});

test("Enter also toggles the focused row", async () => {
  const { host, root, restore } = setupDom();
  let received: string[] | null = null;
  await act(async () => {
    root.render(<Group value={[]} onChange={(next) => (received = next)} />);
  });
  await settle();

  const boxes = host.querySelectorAll<HTMLElement>('[role="checkbox"]');
  await act(async () => {
    boxes[2].dispatchEvent(
      new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }),
    );
  });
  expect(received).toEqual(["c"]);

  await act(async () => root.unmount());
  restore();
});

test("roving tabIndex: exactly one row is tabbable and matches the focused index", async () => {
  const { host, root, restore } = setupDom();
  await act(async () => {
    root.render(<Group value={[]} onChange={() => {}} />);
  });
  await settle();

  const boxes = Array.from(host.querySelectorAll<HTMLElement>('[role="checkbox"]'));
  const tabbable = boxes.filter((b) => b.tabIndex === 0);
  expect(tabbable.length).toBe(1);
  // Default focus index is the first row.
  expect(boxes[0].tabIndex).toBe(0);

  await act(async () => root.unmount());
  restore();
});

test("ArrowDown moves roving focus to the next row", async () => {
  const { host, root, restore } = setupDom();
  await act(async () => {
    root.render(<Group value={[]} onChange={() => {}} />);
  });
  await settle();

  const group = host.querySelector<HTMLElement>('[role="group"]')!;
  const boxes = Array.from(host.querySelectorAll<HTMLElement>('[role="checkbox"]'));
  await act(async () => {
    boxes[0].focus();
  });
  await act(async () => {
    group.dispatchEvent(
      new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true, cancelable: true }),
    );
  });
  await settle();

  expect(boxes[1].tabIndex).toBe(0);
  expect(document.activeElement).toBe(boxes[1]);

  await act(async () => root.unmount());
  restore();
});

test("a row with a description wires aria-describedby to the rendered text", async () => {
  const { host, root, restore } = setupDom();
  await act(async () => {
    root.render(<Group value={[]} onChange={() => {}} />);
  });
  await settle();

  const basil = host.querySelectorAll<HTMLElement>('[role="checkbox"]')[1];
  const descId = basil.getAttribute("aria-describedby");
  expect(descId).toBeTruthy();
  expect(host.querySelector(`#${descId}`)?.textContent).toBe("fresh");

  await act(async () => root.unmount());
  restore();
});
