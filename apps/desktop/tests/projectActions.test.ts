import { afterEach, beforeEach, expect, test } from "bun:test";

import { archiveProject } from "../src/actions/sessions.ts";
import type { Project, SessionListItem } from "../src/api.ts";
import { getState, setState } from "../src/store/index.ts";

const originalWindow = (globalThis as typeof globalThis & { window?: unknown }).window;

beforeEach(() => {
  setState({
    config: { serverUrl: "http://localhost:6877", apiKey: "" },
    projects: [project("p1", "ntrp"), project("p2", "dex")],
    sessions: [
      session("s1", "ntrp bug", "p1"),
      session("s2", "dex bug", "p2"),
      session("s3", "loose note", null),
    ],
  });
});

afterEach(() => {
  (globalThis as typeof globalThis & { window?: unknown }).window = originalWindow;
});

test("archiveProject removes the project and moves its sessions to Inbox locally", async () => {
  const requests: { path: string; method?: string; body?: string; timeout?: number }[] = [];
  (globalThis as typeof globalThis & { window?: unknown }).window = {
    ntrpDesktop: {
      api: {
        request: async (
          _config: unknown,
          req: { path: string; method?: string; body?: string; timeout?: number },
        ) => {
          requests.push(req);
          return {
            ok: true,
            status: 200,
            statusText: "OK",
            contentType: "application/json",
            data: { status: "archived", project_id: "p1" },
            text: "",
          };
        },
      },
    },
  };

  await archiveProject("p1");

  expect(requests).toEqual([{ path: "/projects/p1", method: "DELETE", body: undefined, timeout: 60_000 }]);
  expect(getState().projects.map((p) => p.project_id)).toEqual(["p2"]);
  expect(getState().sessions.map((s) => [s.session_id, s.project_id])).toEqual([
    ["s1", null],
    ["s2", "p2"],
    ["s3", null],
  ]);
});

function project(project_id: string, name: string): Project {
  return {
    project_id,
    name,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    default_cwd: null,
    instructions: null,
    knowledge_scope: `project:${project_id}`,
    archived_at: null,
  };
}

function session(session_id: string, name: string, project_id: string | null): SessionListItem {
  return {
    session_id,
    name,
    project_id,
    started_at: "2026-01-01T00:00:00Z",
    last_activity: "2026-01-01T00:00:00Z",
    message_count: 1,
  };
}
