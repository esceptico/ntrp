import { CopyButton } from "@/features/chat/components/CopyButton";
import { Caption } from "@/components/ui/Caption";

export function Section({
  title,
  body,
  html,
  placeholder,
}: {
  title: string;
  body: string;
  html: string;
  placeholder: string;
}) {
  const hasBody = body.trim().length > 0;

  return (
    <section className="grid grid-cols-[minmax(0,1fr)] gap-1.5 min-w-0">
      <div className="flex items-center gap-2">
        <Caption>{title}</Caption>
        {hasBody && <CopyButton getValue={() => body} />}
      </div>
      {hasBody ? (
        html ? (
          <pre
            className="hljs m-0 p-3 rounded-[10px] bg-code-bg border border-line-soft text-xs leading-[1.55] text-ink-soft font-mono whitespace-pre-wrap [overflow-wrap:anywhere] max-h-[40vh] min-w-0 max-w-full overflow-y-auto overflow-x-hidden scroll-thin"
            dangerouslySetInnerHTML={{ __html: html }}
          />
        ) : (
          <pre className="m-0 p-3 rounded-[10px] bg-code-bg border border-line-soft text-xs leading-[1.55] text-ink-soft font-mono whitespace-pre-wrap [overflow-wrap:anywhere] max-h-[40vh] min-w-0 max-w-full overflow-y-auto overflow-x-hidden scroll-thin">
            {body}
          </pre>
        )
      ) : (
        <div className="px-3 py-2.5 rounded-[10px] bg-surface-soft text-sm text-faint italic">
          {placeholder}
        </div>
      )}
    </section>
  );
}
