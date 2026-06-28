import { beforeEach, expect, test } from "bun:test";
import { getState, setState } from "@/store/index";
import type { Toast } from "@/lib/taskToast";

const toast = (id: string): Toast => ({
  id,
  title: "Done",
  status: "completed",
  target: { kind: "automation" },
});

beforeEach(() => setState({ toasts: [] }));

test("pushToast appends a toast", () => {
  getState().pushToast(toast("x"));
  expect(getState().toasts.map((t) => t.id)).toEqual(["x"]);
});

test("pushToast ignores a duplicate id", () => {
  getState().pushToast(toast("x"));
  getState().pushToast(toast("x"));
  expect(getState().toasts.length).toBe(1);
});

test("dismissToast removes by id", () => {
  getState().pushToast(toast("x"));
  getState().pushToast(toast("y"));
  getState().dismissToast("x");
  expect(getState().toasts.map((t) => t.id)).toEqual(["y"]);
});
