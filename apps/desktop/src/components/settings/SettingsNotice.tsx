export function SettingsConnectionHint({
  title = "Connect the desktop to ntrp first",
  detail = "Check the server URL and API key in the Connection tab, then refresh this view.",
}: {
  title?: string;
  detail?: string;
}) {
  return (
    <div className="rounded-[12px] border border-line-soft bg-surface px-3.5 py-3">
      <div className="text-[13.5px] font-medium text-ink">{title}</div>
      <div className="mt-1 text-[12.5px] text-muted leading-[1.45]">{detail}</div>
    </div>
  );
}

export function SettingsInlineError({ title, message }: { title: string; message: string }) {
  return (
    <div className="grid gap-0.5 px-3 py-2.5 rounded-[10px] bg-bad-soft border border-[rgba(184,68,43,0.16)]">
      <strong className="text-bad text-[12.5px] font-semibold">{title}</strong>
      <span className="text-[12.5px] text-[#8a3220] leading-[1.4]">{message}</span>
    </div>
  );
}
