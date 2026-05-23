import { useEffect, useMemo, useState } from "react";
import type { Project } from "../../api";
import { saveProject } from "../../actions";
import { PageModal } from "../PageModal";

interface ProjectSettingsModalProps {
  project: Project | null;
  onClose: () => void;
}

export function ProjectSettingsModal({ project, onClose }: ProjectSettingsModalProps) {
  const [name, setName] = useState("");
  const [cwd, setCwd] = useState("");
  const [instructions, setInstructions] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!project) return;
    setName(project.name);
    setCwd(project.default_cwd ?? "");
    setInstructions(project.instructions ?? "");
    setError(null);
    setSaving(false);
  }, [project]);

  const canSave = useMemo(() => Boolean(project && name.trim() && !saving), [project, name, saving]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!project || !canSave) return;
    setSaving(true);
    setError(null);
    try {
      await saveProject(project.project_id, {
        name: name.trim(),
        default_cwd: cwd.trim() || null,
        instructions: instructions.trim() || null,
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <PageModal
      open={Boolean(project)}
      onClose={saving ? () => {} : onClose}
      disableEscape={saving}
      size="w-[min(640px,calc(100vw-32px))] h-[min(520px,calc(100vh-32px))]"
      header={{ title: project?.name ?? "Project" }}
    >
      <form onSubmit={submit} className="min-h-0 grid grid-rows-[minmax(0,1fr)_auto]">
        <div className="min-h-0 overflow-y-auto scroll-thin px-5 pb-4 space-y-4">
          <label className="block">
            <span className="block text-xs font-medium uppercase tracking-[0.06em] text-faint mb-1.5">Name</span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              className="w-full px-3 py-2 rounded-md bg-surface-soft border border-line-soft text-sm text-ink outline-none focus:border-accent"
              autoFocus
            />
          </label>
          <label className="block">
            <span className="block text-xs font-medium uppercase tracking-[0.06em] text-faint mb-1.5">Default cwd</span>
            <input
              value={cwd}
              onChange={(event) => setCwd(event.target.value)}
              className="w-full px-3 py-2 rounded-md bg-surface-soft border border-line-soft text-sm font-mono text-ink outline-none focus:border-accent"
              spellCheck={false}
            />
          </label>
          <label className="block">
            <span className="block text-xs font-medium uppercase tracking-[0.06em] text-faint mb-1.5">Instructions</span>
            <textarea
              value={instructions}
              onChange={(event) => setInstructions(event.target.value)}
              className="w-full min-h-[150px] px-3 py-2 rounded-md bg-surface-soft border border-line-soft text-sm text-ink outline-none focus:border-accent resize-none"
            />
          </label>
          {error && <div className="text-sm text-bad">{error}</div>}
        </div>
        <footer className="flex items-center justify-end gap-2 px-5 py-4 border-t border-line-soft">
          <button
            type="button"
            disabled={saving}
            onClick={onClose}
            className="px-3 py-1.5 rounded-md text-sm text-ink-soft hover:text-ink hover:bg-surface-soft disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!canSave}
            className="px-3 py-1.5 rounded-md text-sm font-medium bg-accent text-on-ink disabled:opacity-50"
          >
            Save
          </button>
        </footer>
      </form>
    </PageModal>
  );
}
