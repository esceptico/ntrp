import { afterEach, expect, test } from "bun:test";

import { selectDirectory } from "@/features/sessions/lib/directoryPicker";

afterEach(() => {
  Reflect.deleteProperty(globalThis, "window");
});

test("selectDirectory returns the native directory choice", async () => {
  const calls: unknown[] = [];
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      ntrpDesktop: {
        dialog: {
          selectDirectory: async (options: unknown) => {
            calls.push(options);
            return "/Users/me/src/ntrp";
          },
        },
      },
    },
  });

  await expect(selectDirectory({ defaultPath: "/Users/me" })).resolves.toBe("/Users/me/src/ntrp");
  expect(calls).toEqual([{ defaultPath: "/Users/me" }]);
});

test("selectDirectory returns null when the bridge is unavailable or cancelled", async () => {
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {},
  });
  await expect(selectDirectory()).resolves.toBeNull();

  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      ntrpDesktop: {
        dialog: {
          selectDirectory: async () => null,
        },
      },
    },
  });
  await expect(selectDirectory()).resolves.toBeNull();
});
