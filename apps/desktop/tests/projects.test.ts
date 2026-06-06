import { expect, test } from "bun:test";

import { groupProjectSessions, primarySidebarSessions } from "../src/lib/projects.ts";
import type { Project, SessionListItem } from "../src/api.ts";

const projects: Project[] = [
  {
    project_id: "p1",
    name: "ntrp",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    default_cwd: "/repo",
    instructions: "Keep it small.",
    knowledge_scope: "project:p1",
    archived_at: null,
  },
  {
    project_id: "p2",
    name: "dex",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    default_cwd: null,
    instructions: null,
    knowledge_scope: "project:p2",
    archived_at: null,
  },
];

const sessions: SessionListItem[] = [
  session("s1", "ntrp bug", "p1"),
  session("s2", "loose note", null),
  session("s3", "dex review", "p2"),
];

test("project session grouping keeps inbox and project folders separate", () => {
  expect(groupProjectSessions(projects, sessions, "")).toEqual([
    { project: projects[0], sessions: [sessions[0]] },
    { project: projects[1], sessions: [sessions[2]] },
    { project: null, sessions: [sessions[1]] },
  ]);
});

test("project session grouping filters by chat and project names", () => {
  expect(groupProjectSessions(projects, sessions, "dex")).toEqual([
    { project: projects[1], sessions: [sessions[2]] },
  ]);
});

test("project session grouping keeps empty project folders visible", () => {
  expect(groupProjectSessions(projects, [sessions[0]], "")).toEqual([
    { project: projects[0], sessions: [sessions[0]] },
    { project: projects[1], sessions: [] },
  ]);
});

test("primary sidebar excludes child agent sessions", () => {
  const chat = session("chat", "main chat", "p1");
  const agent = {
    ...session("agent", "research child", "p1"),
    session_type: "agent" as const,
    parent_session_id: "chat",
  };

  expect(primarySidebarSessions([chat, agent])).toEqual([chat]);
});

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
