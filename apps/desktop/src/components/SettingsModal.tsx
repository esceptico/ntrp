import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { useStore } from "../store";
import { saveAndReconnect } from "../actions";

export function SettingsModal() {
  const draft = useStore((s) => s.connectionDraft);
  const setConnectionDraft = useStore((s) => s.setConnectionDraft);
  const error = useStore((s) => s.connectionError);
  const saving = useStore((s) => s.connectionSaving);
  const closeSettings = useStore((s) => s.closeSettings);

  const formRef = useRef<HTMLFormElement>(null);
  const serverInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    serverInputRef.current?.focus();
  }, []);

  function close() {
    if (!saving) closeSettings();
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    void saveAndReconnect(draft);
  }

  const root = document.querySelector("#app");
  if (!root) return null;

  return createPortal(
    <div className="absolute inset-0 z-50 grid place-items-center p-8 bg-[rgba(28,26,22,0.32)] backdrop-blur-md animate-fade-in">
      <form
        ref={formRef}
        onSubmit={submit}
        onKeyDown={(e) => {
          if (e.key === "Escape") close();
        }}
        className="w-[min(520px,calc(100vw-80px))] grid gap-[18px] p-5 pt-[22px] pb-[18px] rounded-2xl bg-surface shadow-[var(--shadow-pop)] animate-pop-in"
      >
        <div className="flex items-start justify-between gap-3.5">
          <div>
            <span className="block mb-1 text-[10.5px] font-medium uppercase tracking-[0.08em] text-accent">
              Connection
            </span>
            <div className="text-[17px] font-semibold tracking-[-0.015em] text-ink">
              Connect to ntrp
            </div>
            <div className="mt-1 text-[12.5px] text-muted leading-[1.45] max-w-[360px]">
              Server URL and API key. Stored locally; encrypted with safeStorage when available.
            </div>
          </div>
          <button
            type="button"
            onClick={close}
            disabled={saving}
            aria-label="Close"
            className="grid place-items-center w-[26px] h-[26px] rounded-md text-muted hover:bg-surface-soft hover:text-ink transition-colors"
          >
            <X size={13} strokeWidth={1.8} />
          </button>
        </div>

        <Field
          label="Server URL"
          value={draft.serverUrl}
          onChange={(serverUrl) => setConnectionDraft({ serverUrl })}
          placeholder="http://localhost:6877"
          help="The address where your ntrp server is running."
        />

        <Field
          label="API key"
          type="password"
          value={draft.apiKey}
          onChange={(apiKey) => setConnectionDraft({ apiKey })}
          placeholder="ntrp_…"
          help="From your server config. Used as a Bearer token."
        />

        {error && (
          <div className="grid gap-0.5 px-3 py-2.5 rounded-[10px] bg-bad-soft border border-[rgba(184,68,43,0.16)]">
            <strong className="text-bad text-[12px] font-semibold">Could not connect</strong>
            <span className="text-[12px] text-[#8a3220] leading-[1.4]">{error}</span>
          </div>
        )}

        <div className="flex items-center gap-2 justify-end pt-1">
          <button
            type="button"
            onClick={close}
            disabled={saving}
            className="inline-flex items-center gap-1.5 h-8 px-3.5 rounded-[9px] bg-surface text-ink-soft border border-line text-[12.5px] font-medium tracking-[-0.005em] hover:bg-surface-soft hover:border-line-strong transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            className="inline-flex items-center gap-1.5 h-8 px-3.5 rounded-[9px] bg-ink text-on-ink text-[12.5px] font-medium tracking-[-0.005em] hover:opacity-90 transition-opacity"
          >
            {saving ? "Checking…" : "Save & reconnect"}
          </button>
        </div>
      </form>
    </div>,
    root,
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  help,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  help?: string;
  type?: "text" | "password";
}) {
  return (
    <div className="grid gap-1">
      <label className="text-[11px] font-medium uppercase tracking-[0.06em] text-muted">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        spellCheck={false}
        autoComplete="off"
        className="w-full h-9 px-3 border border-line rounded-[9px] bg-surface text-ink text-[13px] outline-none hover:border-line-strong focus:border-accent focus:shadow-[0_0_0_3px_var(--color-accent-soft)] transition-[border-color,box-shadow]"
      />
      {help && <span className="text-[11.5px] text-faint leading-[1.4]">{help}</span>}
    </div>
  );
}
