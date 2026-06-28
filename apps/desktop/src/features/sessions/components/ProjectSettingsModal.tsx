import { useEffect, useMemo, useState } from "react";
import { FolderOpen } from "lucide-react";
import type { Project } from "@/api/types";
import { archiveProject, saveProject } from "@/actions";
import { selectDirectory } from "@/features/sessions/lib/directoryPicker";
import { PageModal } from "@/components/ui/PageModal";
import { Button } from "@/components/ui/Button";
import { ConfirmDeleteButton } from "@/components/ui/ConfirmDeleteButton";

interface ProjectSettingsModalProps {
  project: Project | null;
  onClose: () => void;
}

export function ProjectSettingsModal({ project, onClose }: ProjectSettingsModalProps) {
  const [name, setName] = useState("");
  const [cwd, setCwd] = useState("");
  const [instructions, setInstructions] = useState("");
  const [saving, setSaving] = useState(false);
  const [archiving, setArchiving] = useState(false);
  const [pickingCwd, setPickingCwd] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!project) return;
    setName(project.name);
    setCwd(project.default_cwd ?? "");
    setInstructions(project.instructions ?? "");
    setError(null);
    setSaving(false);
    setArchiving(false);
    setPickingCwd(false);
  }, [project]);

  const busy = saving || archiving;
  const canSave = useMemo(() => Boolean(project && name.trim() && !busy), [project, name, busy]);

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

  async function pickCwd() {
    if (busy || pickingCwd) return;
    setPickingCwd(true);
    setError(null);
    try {
      const selected = await selectDirectory({ defaultPath: cwd.trim() || undefined });
      if (selected) setCwd(selected);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setPickingCwd(false);
    }
  }

  async function archive() {
    if (!project || archiving) return;
    setArchiving(true);
    setError(null);
    try {
      await archiveProject(project.project_id);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setArchiving(false);
    }
  }

  return (
    <PageModal
      open={Boolean(project)}
      onClose={busy ? () => {} : onClose}
      disableEscape={busy}
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
              className="w-full px-3 py-2 rounded-md bg-surface-soft border border-line-soft text-sm text-ink outline-none focus:border-accent focus:shadow-[0_0_0_3px_var(--color-accent-soft)] transition-[border-color,box-shadow] duration-row ease-out"
              autoFocus
            />
          </label>
          <label className="block">
            <span className="block text-xs font-medium uppercase tracking-[0.06em] text-faint mb-1.5">Default cwd</span>
            <div className="flex gap-2">
              <input
                value={cwd}
                onChange={(event) => setCwd(event.target.value)}
                className="min-w-0 flex-1 px-3 py-2 rounded-md bg-surface-soft border border-line-soft text-sm font-mono text-ink outline-none focus:border-accent focus:shadow-[0_0_0_3px_var(--color-accent-soft)] transition-[border-color,box-shadow] duration-row ease-out"
                spellCheck={false}
              />
              <Button
                variant="secondary"
                disabled={busy || pickingCwd}
                onClick={pickCwd}
                leadingIcon={FolderOpen}
              >
                Choose
              </Button>
            </div>
          </label>
          <label className="block">
            <span className="block text-xs font-medium uppercase tracking-[0.06em] text-faint mb-1.5">Instructions</span>
            <textarea
              value={instructions}
              onChange={(event) => setInstructions(event.target.value)}
              className="w-full min-h-[150px] px-3 py-2 rounded-md bg-surface-soft border border-line-soft text-sm text-ink outline-none focus:border-accent focus:shadow-[0_0_0_3px_var(--color-accent-soft)] transition-[border-color,box-shadow] duration-row ease-out resize-none"
            />
          </label>
          {error && <div className="text-sm text-bad">{error}</div>}
        </div>
        <footer className="flex items-center justify-between gap-2 px-5 py-4 border-t border-line-soft">
          <ConfirmDeleteButton
            size="md"
            label={`Archive ${project?.name ?? "project"}`}
            busy={busy}
            onConfirm={() => void archive()}
          />
          <div className="flex items-center justify-end gap-2">
            <Button variant="ghost" disabled={busy} onClick={onClose}>
              Cancel
            </Button>
            <Button variant="primary" type="submit" disabled={!canSave}>
              Save
            </Button>
          </div>
        </footer>
      </form>
    </PageModal>
  );
}
