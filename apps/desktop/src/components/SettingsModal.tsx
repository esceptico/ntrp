import { useEffect, useRef, useState } from "react";
import { Boxes, Brain, Cable, Database, KeyRound, Palette, Plug, Sparkles, Wrench, X, type LucideIcon } from "lucide-react";
import { useStore } from "../store";
import type { SettingsTabId } from "../store/types";
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
import { ScrollFadeTop } from "./ScrollBlur";
import { Tab as TabItem, Tabs } from "./ui/Tabs";
import { TabPanels, useTabDirection } from "./ui/TabPanels";

type TabId = SettingsTabId;

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

const SETTINGS_TAB_IDS = TABS.map((t) => t.id);

export function SettingsModal() {
  const open = useStore((s) => s.settingsOpen);
  const requestedTab = useStore((s) => s.settingsTab);
  const closeSettings = useStore((s) => s.closeSettings);
  const saving = useStore((s) => s.connectionSaving);
  const draft = useStore((s) => s.connectionDraft);
  const error = useStore((s) => s.connectionError);
  const setConnectionDraft = useStore((s) => s.setConnectionDraft);
  const serverConfig = useStore((s) => s.serverConfig);
  const formRef = useRef<HTMLFormElement>(null);

  const [active, setActive] = useState<TabId>("connection");
  const direction = useTabDirection(SETTINGS_TAB_IDS, active);

  useEffect(() => {
    if (!open) return;
    // Load (or refresh) server config every time the modal opens — getting
    // fresh values is cheap and keeps the form honest.
    void fetchServerConfig();
  }, [open]);

  // Deep-link: when a caller passes a tab to openSettings, jump there as
  // the modal opens. Only honored on open so manual tab switches aren't
  // clobbered while the modal stays mounted.
  useEffect(() => {
    if (open && requestedTab) setActive(requestedTab);
  }, [open, requestedTab]);

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
      grid="grid-cols-[224px_minmax(0,1fr)] grid-rows-[minmax(0,1fr)]"
      disableEscape={saving}
    >
        <aside className="sidebar surface-panel settings-sidebar-card flex flex-col min-h-0 m-2 overflow-hidden">
          <div className="drag-spacer shrink-0 h-[22px]" />
          <Tabs
            value={active}
            onChange={(v) => setActive(v as TabId)}
            variant="pill"
            orientation="vertical"
            indicatorClassName="bg-[color-mix(in_oklab,var(--color-ink)_4%,transparent)] shadow-[inset_0_0_0_1px_color-mix(in_oklab,var(--color-ink)_10%,transparent)]"
            className="gap-px px-2.5 pt-2 pb-3 overflow-y-auto scroll-thin scroll-fade-bottom"
          >
            {TABS.map((tab) => {
              const Icon = tab.icon;
              return (
                <TabItem
                  key={tab.id}
                  value={tab.id}
                  className="grid w-full grid-cols-[16px_minmax(0,1fr)] items-center gap-2 px-2 py-1 rounded-lg text-base font-medium text-left tracking-[-0.005em] text-ink-soft transition-colors hover:text-ink data-[active=true]:text-ink"
                >
                  <span className="grid h-4 w-4 shrink-0 place-items-center">
                    <Icon size={ICON.LG} strokeWidth={2} />
                  </span>
                  <span className="truncate">{tab.label}</span>
                </TabItem>
              );
            })}
          </Tabs>
        </aside>

        <div className="relative min-h-0 min-w-0">
          <header className="absolute top-0 left-0 right-0 z-10 flex items-center justify-between gap-2 px-5 pt-4 pb-3">
            <div className="text-lg font-semibold tracking-[-0.012em] text-ink">
              {TABS.find((t) => t.id === active)?.label}
            </div>
            <IconButton onClick={close} disabled={saving} aria-label="Close">
              <X size={ICON.SM} strokeWidth={2} />
            </IconButton>
          </header>

          <div className="absolute inset-0 overflow-y-auto overflow-x-hidden scroll-thin px-5 pt-[56px] pb-4">
            <ScrollFadeTop />
            <TabPanels value={active} direction={direction} className="pt-1">
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
            </TabPanels>
          </div>
        </div>
    </PageModal>
  );
}
