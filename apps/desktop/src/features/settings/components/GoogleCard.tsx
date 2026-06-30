import clsx from "clsx";
import { CalendarDays, Mail } from "lucide-react";
import { type GmailAccount } from "@/api/settings";
import { type GoogleConnectionSummary } from "@/features/settings/lib/integrationConnection";
import { ICON } from "@/lib/icons";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { BlurSwap } from "@/components/ui/BlurSwap";
import { Button } from "@/components/ui/Button";
import { ConfirmDeleteButton } from "@/components/ui/ConfirmDeleteButton";
import { SwitchControl } from "@/components/ui/SwitchControl";

export function GoogleCard({
  enabled,
  summary,
  accounts,
  pendingId,
  onToggle,
  onAdd,
  onRemove,
  onAssistant,
}: {
  enabled: boolean;
  summary: GoogleConnectionSummary;
  accounts: GmailAccount[];
  pendingId: string | null;
  onToggle: (enabled: boolean) => Promise<void>;
  onAdd: () => Promise<void>;
  onRemove: (account: GmailAccount) => Promise<void>;
  onAssistant: () => void;
}) {
  const pendingGoogle = pendingId === "google";
  const pendingAdd = pendingId === "gmail:add";
  const summaryTone = {
    ready: "ok",
    paused: "warn",
    setup: "neutral",
  }[summary.tone] as BadgeTone;

  return (
    <section className="rounded-[12px] border border-line-soft bg-surface overflow-hidden">
      <div className="flex flex-wrap items-start gap-3 px-3.5 py-3">
        <div className="min-w-[150px] flex-1 grid gap-1">
          <div className="flex items-center gap-2 min-w-0">
            <GoogleIcon enabled={enabled} />
            <div className="text-base font-medium text-ink truncate">Google Workspace</div>
            <Badge tone={summaryTone}>{summary.label}</Badge>
          </div>
          <div className="text-xs text-muted leading-[1.4]">
            Gmail and Calendar share the same Google account token.
          </div>
          <div className="text-xs text-muted font-mono truncate">
            {summary.detail}
          </div>
        </div>

        <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
          <Button variant="secondary" onClick={onAssistant}>
            Run setup assistant
          </Button>
          <Button variant="secondary" onClick={() => void onAdd()} disabled={pendingAdd}>
            <BlurSwap swapKey={pendingAdd ? "connecting" : "add"} blur={2}>
              {pendingAdd ? "Connecting…" : "Add account"}
            </BlurSwap>
          </Button>
          <SwitchControl
            checked={enabled}
            onChange={(next) => void onToggle(next)}
            disabled={pendingGoogle}
            aria-label="Enable Google Workspace"
          />
        </div>
      </div>

      {accounts.length > 0 && (
        <div className="grid gap-1 px-3.5 py-2.5 bg-surface-soft/35">
          {accounts.map((account) => (
            <div
              key={account.token_file}
              className="grid grid-cols-[minmax(0,1fr)_auto] gap-2 items-center text-sm"
            >
              <div className="min-w-0">
                <div className="text-ink-soft truncate">{account.email || "Unknown account"}</div>
                <div
                  className={clsx(
                    "text-xs truncate",
                    account.error ? "text-bad" : "text-muted",
                  )}
                >
                  {account.error
                    ? account.error
                    : account.has_send_scope
                      ? "Read, send, and calendar access"
                      : "Read and calendar access"}
                </div>
              </div>
              <ConfirmDeleteButton
                size="md"
                label={`Remove ${account.email || account.token_file}`}
                busy={pendingId === `gmail:${account.token_file}`}
                onConfirm={() => void onRemove(account)}
              />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function GoogleIcon({ enabled }: { enabled: boolean }) {
  return (
    <span className="relative grid place-items-center w-4 h-4 shrink-0">
      <Mail size={ICON.MD} strokeWidth={2} className={enabled ? "text-ok" : "text-muted"} />
      <CalendarDays
        size={ICON.XS}
        strokeWidth={1.9}
        className={clsx("absolute -right-1 -bottom-0.5", enabled ? "text-ok" : "text-faint")}
      />
    </span>
  );
}
