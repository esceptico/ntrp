import { Plus, Trash2 } from "lucide-react";
import { ICON } from "@/lib/icons";
import { Button } from "@/components/ui/Button";
import { IconButton } from "@/components/ui/IconButton";

export function AddBtn({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <Button variant="ghost" leadingIcon={Plus} onClick={onClick}>
      {label}
    </Button>
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
    <div className="px-3 py-6 rounded-[10px] bg-bg-main/40 text-sm text-muted italic text-center">
      {children}
    </div>
  );
}
