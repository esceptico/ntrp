import { describe, expect, test } from "bun:test";
import {
  automationEventsUrl,
  reduceAutomationStreamCursor,
} from "../src/hooks/useAutomationEvents";

describe("automation event stream helpers", () => {
  test("automationEventsUrl resumes from the last seen seq", () => {
    expect(automationEventsUrl("http://127.0.0.1:8000", undefined)).toBe(
      "http://127.0.0.1:8000/automations/events",
    );
    expect(automationEventsUrl("http://127.0.0.1:8000", 42)).toBe(
      "http://127.0.0.1:8000/automations/events?after_seq=42",
    );
    expect(automationEventsUrl("http://127.0.0.1:8000/api", 42)).toBe(
      "http://127.0.0.1:8000/api/automations/events?after_seq=42",
    );
  });

  test("reduceAutomationStreamCursor advances on event seq and keepalive latest seq", () => {
    expect(reduceAutomationStreamCursor(undefined, { type: "automation_progress", seq: 2 })).toBe(2);
    expect(reduceAutomationStreamCursor(2, { type: "stream_keepalive", latest_seq: 9 })).toBe(9);
    expect(reduceAutomationStreamCursor(9, { type: "automation_finished", seq: 4 })).toBe(9);
  });
});
