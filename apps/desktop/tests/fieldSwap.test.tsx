import { expect, test } from "bun:test";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { FieldSwap } from "@/components/ui/FieldSwap";

test("FieldSwap renders current children for a stable key", async () => {
  const el = document.createElement("div");
  const root = createRoot(el);
  await act(async () => root.render(<FieldSwap swapKey="a" dir={0}><span>alpha</span></FieldSwap>));
  expect(el.textContent).toBe("alpha");
  await act(async () => root.render(<FieldSwap swapKey="b" dir={0}><span>beta</span></FieldSwap>));
  expect(el.textContent).toBe("beta");  // dir=0 → instant swap, no phases
});
