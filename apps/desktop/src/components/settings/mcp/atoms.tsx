import { Plus, Trash2 } from "lucide-react";
import { ICON } from "../../../lib/icons";
import { IconButton } from "../../IconButton";

export function AddBtn({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center justify-center gap-1.5 h-8 rounded-md bg-surface-soft hover:bg-surface-soft/80 text-sm text-muted hover:text-ink transition-colors"
    >
      <Plus size={ICON.XS} strokeWidth={2} /> {label}
    </button>
  );
}

export function RemoveBtn({ onClick }: { onClick: () => void }) {
  return (
    <IconButton size="lg" tone="faint" onClick={onClick} aria-label="Remove">
      <Trash2 size={ICON.SM} strokeWidth={2} />
    </IconButton>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-3 py-6 rounded-[10px] bg-bg-main/40 text-sm text-faint italic text-center">
      {children}
    </div>
  );
}
