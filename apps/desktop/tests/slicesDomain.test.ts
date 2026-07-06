import { expect, test } from "bun:test";
import {
  createSlicesDomainState,
  reduceOverviewLoaded,
  reduceAskResolved,
  reduceOpenSlice,
} from "@/stores/slices-domain";

const ask = {
  id: "a1",
  slice_key: "o-1a",
  text: "t",
  kind: "review" as const,
  source: "agent",
  actions: [],
  state: "active",
  created_at: "2026-07-06",
  snoozed_until: null,
};
const overview = {
  slices: [
    {
      key: "o-1a",
      title: "O-1A",
      autonomy: "observe" as const,
      live: true,
      updated: "",
      ask_count: 1,
    },
  ],
  focus: [ask],
};

test("overview load + ask resolve removes from focus", () => {
  let s = reduceOverviewLoaded(createSlicesDomainState(), overview);
  expect(s.overview?.focus.length).toBe(1);
  s = reduceAskResolved(s, "o-1a", "a1");
  expect(s.overview?.focus.length).toBe(0);
});

test("openSlice sets and clears the room", () => {
  let s = reduceOpenSlice(createSlicesDomainState(), "o-1a");
  expect(s.openSliceKey).toBe("o-1a");
  expect(reduceOpenSlice(s, null).openSliceKey).toBeNull();
});
