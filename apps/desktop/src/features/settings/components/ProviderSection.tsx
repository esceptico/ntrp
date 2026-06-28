import { type ReactNode } from "react";
import { SectionHeader } from "@/components/ui/SectionHeader";

export function ProviderSection({
  title,
  detail,
  empty,
  children,
}: {
  title: string;
  detail: string;
  empty: string;
  children: ReactNode;
}) {
  const childCount = Array.isArray(children) ? children.length : children ? 1 : 0;

  return (
    <section className="grid gap-2">
      <SectionHeader label={title} detail={detail} className="px-0.5" />
      {childCount > 0 ? (
        <div className="grid gap-2">{children}</div>
      ) : (
        <div className="rounded-[10px] border border-line-soft bg-surface px-3 py-2 text-sm text-muted">
          {empty}
        </div>
      )}
    </section>
  );
}
