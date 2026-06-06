import type { Project, SessionListItem } from "../api";

export interface ProjectSessionGroup {
  project: Project | null;
  sessions: SessionListItem[];
}

export function primarySidebarSessions(sessions: SessionListItem[]): SessionListItem[] {
  return sessions.filter((session) => session.session_type !== "agent");
}

export function groupProjectSessions(
  projects: Project[],
  sessions: SessionListItem[],
  query: string,
): ProjectSessionGroup[] {
  const q = query.trim().toLowerCase();
  const projectById = new Map(projects.map((project) => [project.project_id, project]));
  const sessionsByProject = new Map<string | null, SessionListItem[]>();

  for (const session of sessions) {
    const projectId = session.project_id && projectById.has(session.project_id) ? session.project_id : null;
    const project = projectId ? projectById.get(projectId) : null;
    const matches =
      !q ||
      (session.name ?? "untitled").toLowerCase().includes(q) ||
      Boolean(project?.name.toLowerCase().includes(q));
    if (!matches) continue;
    const bucket = sessionsByProject.get(projectId) ?? [];
    bucket.push(session);
    sessionsByProject.set(projectId, bucket);
  }

  const groups: ProjectSessionGroup[] = [];
  for (const project of projects) {
    const projectSessions = sessionsByProject.get(project.project_id) ?? [];
    const projectMatches = !q || project.name.toLowerCase().includes(q);
    if (projectSessions.length || projectMatches) groups.push({ project, sessions: projectSessions });
  }
  const inbox = sessionsByProject.get(null);
  if (inbox?.length) groups.push({ project: null, sessions: inbox });
  return groups;
}
