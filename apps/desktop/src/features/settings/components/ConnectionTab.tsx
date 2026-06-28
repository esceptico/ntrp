import { Field } from "@/features/settings/components/Field";
import type { AppConfig } from "@/api";
import { BlurSwap } from "@/components/ui/BlurSwap";
import { SettingsInlineError } from "@/features/settings/components/SettingsNotice";

export function ConnectionTab({
  formRef,
  draft,
  error,
  saving,
  onUpdate,
  onSubmit,
}: {
  formRef: React.RefObject<HTMLFormElement | null>;
  draft: AppConfig;
  error: string | null;
  saving: boolean;
  onUpdate: (patch: Partial<AppConfig>) => void;
  onSubmit: (e: React.FormEvent) => void;
}) {
  return (
    <form ref={formRef} onSubmit={onSubmit} className="grid gap-4">
      <p className="text-sm text-muted leading-[1.45] max-w-[440px]">
        Server URL and API key. Stored locally; encrypted with safeStorage when available.
      </p>

      <Field
        label="Server URL"
        value={draft.serverUrl}
        onChange={(v) => onUpdate({ serverUrl: v })}
        placeholder="http://localhost:6877"
        help="The address where your ntrp server is running."
      />

      <Field
        label="API key"
        type="password"
        value={draft.apiKey}
        onChange={(v) => onUpdate({ apiKey: v })}
        placeholder="ntrp_…"
        help="From your server config. Used as a Bearer token."
      />

      {error && <SettingsInlineError title="Could not connect" message={error} />}

      <div className="flex justify-end pt-1">
        <button
          type="submit"
          disabled={saving}
          className="inline-flex items-center gap-1.5 h-8 px-3.5 rounded-[9px] bg-ink text-on-ink text-sm font-medium tracking-[-0.005em] hover:opacity-90 transition-[opacity,scale] duration-check ease-out active:scale-[0.97]"
        >
          <BlurSwap swapKey={saving ? "checking" : "save"} blur={2}>
            {saving ? "Checking…" : "Save & reconnect"}
          </BlurSwap>
        </button>
      </div>
    </form>
  );
}
