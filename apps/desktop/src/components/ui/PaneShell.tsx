import type { ReactNode } from "react";
import clsx from "clsx";
import { ScrollFadeTop } from "@/components/ui/ScrollBlur";

export function PaneShell({
  list,
  detail,
  /** Fixed 280px list column with a hard divider (file-tree layout) instead
   *  of the default resizable minmax(280,360). */
  fixedList = false,
  /** Skip the detail-pane scroll container — the caller owns its own scroll
   *  (e.g. DetailShell, which already scrolls its body). */
  scrollDetail = true,
}: {
  list: ReactNode;
  detail: ReactNode;
  fixedList?: boolean;
  scrollDetail?: boolean;
}) {
  return (
    <div
      className={clsx(
        "grid h-full",
        fixedList ? "grid-cols-[280px_minmax(0,1fr)]" : "grid-cols-[minmax(280px,360px)_minmax(0,1fr)]",
      )}
    >
      <div className={clsx("flex flex-col min-h-0", fixedList && "border-r border-line-soft")}>{list}</div>
      {scrollDetail ? (
        <div className="min-h-0 overflow-y-auto scroll-thin">
          <ScrollFadeTop />
          {detail}
        </div>
      ) : (
        <div className="min-h-0">{detail}</div>
      )}
    </div>
  );
}
