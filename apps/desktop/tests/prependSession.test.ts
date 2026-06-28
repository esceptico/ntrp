import { beforeEach, expect, test } from "bun:test";
import { getState, setState } from "@/store/index";
import type { SessionListItem } from "@/api";

function row(id: string, name = id): SessionListItem {
  return {
    session_id: id,
    started_at: "2026-05-30T00:00:00Z",
    last_activity: "2026-05-30T00:00:00Z",
    name,
    message_count: 0,
    session_type: "channel",
  };
}

beforeEach(() => {
  setState({ sessions: [], activeRunSessionIds: new Set() });
});

test("prependSession adds a new session to the front", () => {
  getState().prependSession(row("a"));
  getState().prependSession(row("b"));
  expect(getState().sessions.map((s) => s.session_id)).toEqual(["b", "a"]);
});

test("prependSession dedupes an already-present id (session_created after bootstrap)", () => {
  getState().setSessions([row("a")]);
  getState().prependSession(row("a", "renamed"));

  expect(getState().sessions.map((s) => s.session_id)).toEqual(["a"]);
  // The existing row is preserved, not replaced by the duplicate.
  expect(getState().sessions[0]?.name).toBe("a");
});

test("patchSession bumps an existing channel row to the front with fresh metadata", () => {
  getState().setSessions([row("a"), row("b"), row("c")]);
  getState().patchSession({ ...row("c"), message_count: 4, last_activity: "2026-05-30T01:00:00Z" });

  expect(getState().sessions.map((s) => s.session_id)).toEqual(["c", "a", "b"]);
  expect(getState().sessions[0]?.message_count).toBe(4);
  expect(getState().sessions[0]?.last_activity).toBe("2026-05-30T01:00:00Z");
});

test("patchSession preserves poll-maintained runtime fields the delta omits", () => {
  getState().setSessions([{ ...row("a"), is_active: true, run_status: "running" }]);
  // Activity delta carries no runtime fields.
  getState().patchSession({ ...row("a"), message_count: 2 });

  expect(getState().sessions[0]?.is_active).toBe(true);
  expect(getState().sessions[0]?.run_status).toBe("running");
  expect(getState().sessions[0]?.message_count).toBe(2);
});

test("patchSession inserts at the front when the session is not yet present", () => {
  getState().setSessions([row("a")]);
  getState().patchSession(row("z"));

  expect(getState().sessions.map((s) => s.session_id)).toEqual(["z", "a"]);
});
