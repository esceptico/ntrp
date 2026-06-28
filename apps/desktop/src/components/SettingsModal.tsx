import { useEffect, useRef, useState } from "react";
import { Archive, Boxes, Brain, Cable, Database, KeyRound, Palette, Plug, Sparkles, Wrench, X, type LucideIcon } from "lucide-react";
import { useStore } from "@/store";
import type { SettingsTabId } from "@/store/types";
import { saveAndReconnect, fetchServerConfig } from "@/actions";
import { ConnectionTab } from "@/components/settings/ConnectionTab";
import { ProvidersTab } from "@/components/settings/ProvidersTab";
import { IntegrationsTab } from "@/components/settings/IntegrationsTab";
import { ModelsTab } from "@/components/settings/ModelsTab";
import { AgentTab } from "@/components/settings/AgentTab";
import { ContextTab } from "@/components/settings/ContextTab";
import { MCPTab } from "@/components/settings/mcp/MCPTab";
import { ToolsTab } from "@/components/settings/ToolsTab";
import { AppearanceTab } from "@/components/settings/AppearanceTab";
import { ArchiveTab } from "@/components/settings/ArchiveTab";
import { PageModal } from "@/components/PageModal";
import { IconButton } from "@/components/IconButton";
import { BlurSwap } from "@/components/BlurSwap";
import { ICON } from "@/lib/icons";
import { ScrollFadeTop } from "@/components/ScrollBlur";
import { Tab as TabItem, Tabs } from "@/components/ui/Tabs";
import { TabPanels, useTabDirection } from "@/components/ui/TabPanels";

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
  { id: "archive", label: "Archived", icon: Archive },
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

  // Deep-link: each time the modal opens, land on the requested tab (e.g.
  // ⌘K → Archived) or fall back to Connection. Resetting on every open keeps
  // a one-off deep-link from stickily hijacking the next normal open, while
  // manual tab switches still persist while the modal stays mounted.
  useEffect(() => {
    if (open) setActive(requestedTab ?? "connection");
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
      ariaLabel="Settings"
    >
        <aside className="sidebar settings-sidebar-card flex flex-col min-h-0 m-2 overflow-hidden">
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
              <BlurSwap swapKey={active} className="justify-items-start">
                {TABS.find((t) => t.id === active)?.label}
              </BlurSwap>
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
              {active === "archive" && <ArchiveTab />}
            </TabPanels>
          </div>
        </div>
    </PageModal>
  );
}
