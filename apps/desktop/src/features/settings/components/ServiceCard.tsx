import { type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { CheckCircle2, KeyRound, MessageCircle, RefreshCw } from "lucide-react";
import { type ServiceConnection } from "@/api/settings";
import { SectionHeader } from "@/components/ui/SectionHeader";
import {
  serviceActionLabel,
  serviceConnectionPill,
} from "@/features/settings/lib/integrationConnection";
import { DISSOLVE_OUT, EASE_OUT, MOTION, RISE_IN, RISE_SETTLED } from "@/lib/tokens/motion";
import { ICON } from "@/lib/icons";
import { BlurSwap } from "@/components/ui/BlurSwap";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

export function ServiceCard({
  connectedServices,
  setupServices,
  editingId,
  serviceKey,
  pendingId,
  onEdit,
  onCancel,
  onKeyChange,
  onConnect,
  onDisconnect,
  onAssistant,
}: {
  connectedServices: ServiceConnection[];
  setupServices: ServiceConnection[];
  editingId: string | null;
  serviceKey: string;
  pendingId: string | null;
  onEdit: (service: ServiceConnection) => void;
  onCancel: () => void;
  onKeyChange: (value: string) => void;
  onConnect: (service: ServiceConnection) => Promise<void>;
  onDisconnect: (service: ServiceConnection) => Promise<void>;
  onAssistant: () => void;
}) {
  return (
    <section className="rounded-[12px] border border-line-soft bg-surface overflow-hidden">
      <div className="px-3.5 py-3 border-b border-line-soft">
        <div className="flex items-center gap-2">
          <MessageCircle size={ICON.MD} strokeWidth={2} className="text-muted" />
          <div className="text-base font-medium text-ink">Slack</div>
        </div>
        <div className="mt-1 text-xs text-muted leading-[1.4]">
          Token-backed Slack tools. OAuth MCP servers stay in the MCP tab.
        </div>
        <Button variant="secondary" onClick={onAssistant} className="mt-2">
          Run setup assistant
        </Button>
      </div>

      {connectedServices.length + setupServices.length === 0 ? (
        <div className="px-3.5 py-3 text-sm text-muted">No token-backed services are registered.</div>
      ) : (
        <div className="grid gap-3 px-3.5 py-3">
          <ServiceSection title="Ready" empty="No Slack tokens connected.">
            {connectedServices.map((service) => (
              <ServiceRow
                key={service.id}
                service={service}
                editing={editingId === service.id}
                serviceKey={editingId === service.id ? serviceKey : ""}
                pending={pendingId === service.id}
                onEdit={() => onEdit(service)}
                onCancel={onCancel}
                onKeyChange={onKeyChange}
                onConnect={() => void onConnect(service)}
                onDisconnect={() => void onDisconnect(service)}
              />
            ))}
          </ServiceSection>
          <ServiceSection title="Set up" empty="All Slack token services are connected.">
            {setupServices.map((service) => (
              <ServiceRow
                key={service.id}
                service={service}
                editing={editingId === service.id}
                serviceKey={editingId === service.id ? serviceKey : ""}
                pending={pendingId === service.id}
                onEdit={() => onEdit(service)}
                onCancel={onCancel}
                onKeyChange={onKeyChange}
                onConnect={() => void onConnect(service)}
                onDisconnect={() => void onDisconnect(service)}
              />
            ))}
          </ServiceSection>
        </div>
      )}
    </section>
  );
}

function ServiceSection({
  title,
  empty,
  children,
}: {
  title: string;
  empty: string;
  children: ReactNode;
}) {
  const childCount = Array.isArray(children) ? children.length : children ? 1 : 0;
  return (
    <section className="grid gap-2">
      <SectionHeader label={title} />
      {childCount > 0 ? (
        <div className="grid gap-2">{children}</div>
      ) : (
        <div className="rounded-[9px] border border-line-soft bg-surface-soft/45 px-3 py-2 text-sm text-muted">
          {empty}
        </div>
      )}
    </section>
  );
}

function ServiceRow({
  service,
  editing,
  serviceKey,
  pending,
  onEdit,
  onCancel,
  onKeyChange,
  onConnect,
  onDisconnect,
}: {
  service: ServiceConnection;
  editing: boolean;
  serviceKey: string;
  pending: boolean;
  onEdit: () => void;
  onCancel: () => void;
  onKeyChange: (value: string) => void;
  onConnect: () => void;
  onDisconnect: () => void;
}) {
  const actionLabel = pending ? "Working…" : serviceActionLabel(service);
  const readOnly = service.connected && service.from_env;
  const connectionPill = serviceConnectionPill(service);

  return (
    <div className="rounded-[10px] border border-line-soft bg-surface overflow-hidden">
      <div className="flex flex-wrap items-start gap-3 px-3 py-2.5">
        <div className="min-w-[150px] flex-1 grid gap-1">
          <div className="flex items-center gap-2 min-w-0">
            <ProviderDot connected={service.connected} />
            <div className="text-sm font-medium text-ink-soft truncate">{service.name}</div>
          </div>
          {connectionPill && <div className="text-xs text-muted font-mono truncate">{connectionPill}</div>}
        </div>
        <div className="ml-auto flex justify-end">
          {readOnly ? (
            <span className="inline-flex items-center h-8 px-3 rounded-md border border-line-soft bg-surface-soft text-sm font-medium text-muted">
              {actionLabel}
            </span>
          ) : (
            <Button
              variant={service.connected ? "secondary" : "primary"}
              onClick={service.connected ? onDisconnect : onEdit}
              disabled={pending}
            >
              <BlurSwap swapKey={actionLabel} blur={2}>
                {actionLabel}
              </BlurSwap>
            </Button>
          )}
        </div>
      </div>

      <AnimatePresence initial={false}>
        {editing && !service.connected && (
          <motion.div
            key="token-editor"
            initial={{ ...RISE_IN, y: -4 }}
            animate={RISE_SETTLED}
            exit={{ ...DISSOLVE_OUT, transition: { duration: MOTION.fast, ease: EASE_OUT } }}
            transition={{ duration: MOTION.row, ease: EASE_OUT }}
            className="grid grid-cols-[minmax(0,1fr)_auto_auto] gap-2 px-3 py-3 bg-surface-soft/35"
          >
            <Input
              type="password"
              value={serviceKey}
              onChange={(event) => onKeyChange(event.target.value)}
              placeholder="Token"
              aria-label="Token"
              autoFocus
              spellCheck={false}
              autoComplete="off"
            />
            <Button onClick={onConnect} disabled={!serviceKey.trim() || pending}>
              {pending && <RefreshCw size={ICON.SM} strokeWidth={2} className="animate-spin" />}
              Connect
            </Button>
            <Button variant="secondary" onClick={onCancel}>
              Cancel
            </Button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function ProviderDot({ connected }: { connected: boolean }) {
  if (connected) {
    return <CheckCircle2 size={ICON.MD} strokeWidth={2} className="text-ok shrink-0" />;
  }
  return <KeyRound size={ICON.MD} strokeWidth={2} className="text-faint shrink-0" />;
}
