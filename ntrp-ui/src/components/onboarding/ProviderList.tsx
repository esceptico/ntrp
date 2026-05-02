import { Dialog, colors, SelectList, type SelectOption } from "../ui/index.js";
import type { ProviderInfo } from "../../api/client.js";
import { getStringModels } from "../../hooks/useOnboardingState.js";

export interface ProviderListProps {
  providers: ProviderInfo[];
  hasConnected: boolean;
  closable: boolean;
  saving: boolean;
  error?: string | null;
  isActive: boolean;
  onSelect: (providerId: string) => void;
  onClose: () => void;
  onDone: () => void;
}

export function ProviderList({ providers, hasConnected, closable, saving, error, isActive, onSelect, onClose, onDone }: ProviderListProps) {
  const subtitle = closable
    ? "Manage providers and API keys"
    : hasConnected
      ? "Add another provider or press esc to start"
      : "Connect an LLM provider to get started";

  const providerOptions: SelectOption[] = providers.map(p => {
    let description = "";
    if (p.id === "custom") {
      const count = p.model_count ?? 0;
      if (count > 0) description = `${count} model${count !== 1 ? "s" : ""}`;
    } else {
      const parts: string[] = [];
      if (p.connected) parts.push("\u2713");
      if (p.connected && p.key_hint) parts.push(p.key_hint);
      if (!p.connected && p.auth_type === "oauth") parts.push("browser sign-in");
      if (p.from_env) parts.push("(env)");
      description = parts.join(" ");
    }
    return { value: p.id, title: p.name, description };
  });

  const providerClose = () => {
    if (hasConnected) onDone();
    else if (closable) onClose();
  };

  return (
    <Dialog
      title="PROVIDERS"
      size="medium"
      onClose={providerClose}
      closable={hasConnected || closable}
      footer={<text><span fg={error ? colors.status.error : colors.text.muted}>{error ?? subtitle}</span></text>}
    >
      {({ height }) => (
        <SelectList
          options={providerOptions}
          visibleLines={height}
          isActive={isActive && !saving}
          onSelect={(opt) => onSelect(opt.value)}
          onClose={providerClose}
          renderItem={(opt, ctx) => {
            const provider = providers.find(p => p.id === opt.value);
            if (!provider) return <text><span fg={ctx.colors.text}>{opt.title}</span></text>;

            if (provider.id === "custom") {
              return (
                <text>
                  <span fg={ctx.colors.text}>{provider.name}</span>
                  {opt.description && <span fg={colors.text.muted}> {opt.description}</span>}
                </text>
              );
            }

            const modelNames = getStringModels(provider).slice(0, 3).join(", ");

            return (
              <box flexDirection="column">
                <text>
                  <span fg={ctx.colors.text}>{provider.name}</span>
                  {provider.connected && <span fg={colors.status.success}>{" \u2713"}</span>}
                  {provider.connected && provider.key_hint && <span fg={colors.text.disabled}>{` ${provider.key_hint}`}</span>}
                  {!provider.connected && provider.auth_type === "oauth" && <span fg={colors.text.disabled}>{" browser sign-in"}</span>}
                  {provider.from_env && <span fg={colors.text.muted}>{" (env)"}</span>}
                </text>
                {modelNames && (
                  <text><span fg={colors.text.disabled}>{"  "}{modelNames}</span></text>
                )}
              </box>
            );
          }}
        />
      )}
    </Dialog>
  );
}
