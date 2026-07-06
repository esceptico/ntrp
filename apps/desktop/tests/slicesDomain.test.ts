import { expect, test } from "bun:test";
import { getState } from "@/stores/index";
import {
  createSlicesDomainState,
  reduceOverviewLoaded,
  reduceAskResolved,
  reduceOpenSlice,
  reduceDetailLoaded,
  reduceAutonomyUpdated,
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

const detail = {
  key: "o-1a",
  title: "O-1A",
  autonomy: "observe" as const,
  page_path: "topics/o-1a.md",
  related: [],
  open_loops: [],
  updated: "",
  asks: [],
  sessions: [],
  automations: [],
};

test("autonomy update patches both cached detail and overview summary", () => {
  let s = reduceOverviewLoaded(createSlicesDomainState(), overview);
  s = reduceDetailLoaded(s, detail);
  s = reduceAutonomyUpdated(s, "o-1a", "act");
  expect(s.detailByKey["o-1a"].autonomy).toBe("act");
  expect(s.overview?.slices[0].autonomy).toBe("act");
});

test("autonomy update is a no-op when the slice has no cached detail", () => {
  const s = reduceAutonomyUpdated(createSlicesDomainState(), "unknown", "act");
  expect(s.detailByKey["unknown"]).toBeUndefined();
});

test("setCurrentSession closes an open slice room (navigating away from a slice)", () => {
  getState().openSlice("o-1a");
  expect(getState().slices.openSliceKey).toBe("o-1a");

  getState().setCurrentSession("s1");

  expect(getState().slices.openSliceKey).toBeNull();
});
