import { useEffect, useRef, useState } from "react";
import { Boxes, Brain, Cable, Database, KeyRound, Palette, Plug, Sparkles, Wrench, X, type LucideIcon } from "lucide-react";
import { useStore } from "../store";
import { saveAndReconnect, fetchServerConfig } from "../actions";
import { ConnectionTab } from "./settings/ConnectionTab";
import { ProvidersTab } from "./settings/ProvidersTab";
import { IntegrationsTab } from "./settings/IntegrationsTab";
import { ModelsTab } from "./settings/ModelsTab";
import { AgentTab } from "./settings/AgentTab";
import { ContextTab } from "./settings/ContextTab";
import { MCPTab } from "./settings/mcp/MCPTab";
import { ToolsTab } from "./settings/ToolsTab";
import { AppearanceTab } from "./settings/AppearanceTab";
import { PageModal } from "./PageModal";
import { IconButton } from "./IconButton";
import { ICON } from "../lib/icons";

type TabId = "connection" | "providers" | "integrations" | "models" | "agent" | "context" | "tools" | "mcp" | "appearance";

interface Tab {
  id: TabId;
  label: string;
  icon: LucideIcon;
}

const TABS: Tab[] = [
  { id: "connection", label: "Connection", icon: Plug },
  { id: "providers", label: "Providers", icon: KeyRound },
  { id: "integrations", label: "Integrations", icon: Cable },
  { id: "models", label: "Models", icon: Sparkles },
  { id: "agent", label: "Agent", icon: Brain },
  { id: "context", label: "Context", icon: Database },
  { id: "tools", label: "Tools", icon: Wrench },
  { id: "mcp", label: "MCP servers", icon: Boxes },
  { id: "appearance", label: "Appearance", icon: Palette },
];

export function SettingsModal() {
  const open = useStore((s) => s.settingsOpen);
  const closeSettings = useStore((s) => s.closeSettings);
  const saving = useStore((s) => s.connectionSaving);
  const draft = useStore((s) => s.connectionDraft);
  const error = useStore((s) => s.connectionError);
  const setConnectionDraft = useStore((s) => s.setConnectionDraft);
  const serverConfig = useStore((s) => s.serverConfig);
  const formRef = useRef<HTMLFormElement>(null);

  const [active, setActive] = useState<TabId>("connection");

  useEffect(() => {
    if (!open) return;
    // Load (or refresh) server config every time the modal opens — getting
    // fresh values is cheap and keeps the form honest.
    void fetchServerConfig();
  }, [open]);

  function close() {
    if (!saving) closeSettings();
  }

  function submitConnection(event: React.FormEvent) {
    event.preventDefault();
    void saveAndReconnect(draft);
  }

  return (
    <PageModal
      open={open}
      onClose={close}
      size="w-[min(1000px,calc(100vw-32px))] h-[min(740px,calc(100vh-32px))] sm:w-[min(1000px,calc(100vw-64px))] sm:h-[min(740px,calc(100vh-64px))]"
      grid="grid-cols-[180px_minmax(0,1fr)] grid-rows-[minmax(0,1fr)]"
      disableEscape={saving}
    >
        <aside className="border-r border-line-soft flex flex-col min-h-0">
          <div className="px-3 pt-4 pb-2 text-2xs font-medium uppercase tracking-[0.08em] text-faint">
            Settings
          </div>
          <nav className="flex flex-col gap-px px-2 pb-3 overflow-y-auto scroll-thin">
            {TABS.map((tab) => {
              const Icon = tab.icon;
              const isActive = active === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActive(tab.id)}
                  data-active={isActive ? "true" : undefined}
                  className="app-row flex items-center gap-2 px-2.5 py-1.5 rounded-md text-base font-medium tracking-[-0.005em] text-ink-soft text-left"
                >
                  <Icon size={ICON.SM} strokeWidth={2} className="shrink-0" />
                  {tab.label}
                </button>
              );
            })}
          </nav>
          <div className="mt-auto px-3 pb-3 text-2xs text-faint shrink-0">
            <button
              type="button"
              onClick={close}
              disabled={saving}
              className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink transition-colors"
            >
              Close
            </button>
          </div>
        </aside>

        <div className="grid grid-rows-[auto_minmax(0,1fr)] min-h-0 min-w-0">
          <header className="flex items-center justify-between gap-2 px-5 pt-4 pb-3 border-b border-line-soft">
            <div className="text-lg font-semibold tracking-[-0.012em] text-ink">
              {TABS.find((t) => t.id === active)?.label}
            </div>
            <IconButton onClick={close} disabled={saving} aria-label="Close">
              <X size={ICON.SM} strokeWidth={2} />
            </IconButton>
          </header>

          <div className="overflow-y-auto scroll-thin px-5 py-4">
            {active === "connection" && (
              <ConnectionTab
                formRef={formRef}
                draft={draft}
                error={error}
                saving={saving}
                onUpdate={setConnectionDraft}
                onSubmit={submitConnection}
              />
            )}
            {active === "providers" && <ProvidersTab />}
            {active === "integrations" && <IntegrationsTab />}
            {active === "models" && <ModelsTab />}
            {active === "agent" && <AgentTab serverConfig={serverConfig} />}
            {active === "context" && <ContextTab serverConfig={serverConfig} />}
            {active === "tools" && <ToolsTab />}
            {active === "mcp" && <MCPTab />}
            {active === "appearance" && <AppearanceTab />}
          </div>
        </div>
    </PageModal>
  );
}
