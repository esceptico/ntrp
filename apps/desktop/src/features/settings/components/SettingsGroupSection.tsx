import { type ReactNode } from "react";
import { SectionHeader } from "@/components/ui/SectionHeader";

export function SettingsGroupSection({
  title,
  detail,
  empty,
  headerClassName,
  emptyClassName = "rounded-[10px] border border-line-soft bg-surface",
  children,
}: {
  title: string;
  detail?: string;
  empty: string;
  headerClassName?: string;
  emptyClassName?: string;
  children: ReactNode;
}) {
  const childCount = Array.isArray(children) ? children.length : children ? 1 : 0;

  return (
    <section className="grid gap-2">
      <SectionHeader label={title} detail={detail} className={headerClassName} />
      {childCount > 0 ? (
        <div className="grid gap-2">{children}</div>
      ) : (
        <div className={`${emptyClassName} px-3 py-2 text-sm text-muted`}>{empty}</div>
      )}
    </section>
  );
}
