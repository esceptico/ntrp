import { colors, BaseSelectionList, type RenderItemContext } from "../../../ui/index.js";
import { Header } from "../SettingsRows.js";
import { SIDEBAR_SECTION_IDS, type SidebarSettings, type SidebarSectionId, type UiSettings } from "../../../../hooks/useSettings.js";

const SIDEBAR_LABELS: Record<SidebarSectionId, string> = {
  models: "Models",
  context: "Context",
  usage: "Usage",
  integrations: "Integrations",
  automations: "Automations",
  sessions: "Sessions",
  memory_stats: "Memory",
};

type InterfaceItem =
  | { type: "toggle"; label: string; enabled: boolean; header?: string; firstHeader?: boolean };

interface InterfaceSectionProps {
  ui: UiSettings;
  sidebar: SidebarSettings;
  selectedIndex: number;
  accent: string;
  height: number;
}

function buildItems(ui: UiSettings, sidebar: SidebarSettings): InterfaceItem[] {
  const items: InterfaceItem[] = [
    { type: "toggle", label: "Enabled", enabled: ui.streaming, header: "Streaming", firstHeader: true },
    { type: "toggle", label: "Show reasoning", enabled: ui.showReasoning, header: "Reasoning" },
  ];

  for (let i = 0; i < SIDEBAR_SECTION_IDS.length; i++) {
    const id = SIDEBAR_SECTION_IDS[i];
    items.push({
      type: "toggle",
      label: SIDEBAR_LABELS[id],
      enabled: sidebar[id],
      header: i === 0 ? "Sidebar panels" : undefined,
    });
  }

  return items;
}

function renderItem(item: InterfaceItem, ctx: RenderItemContext) {
  const content = (
    <text>
      <span fg={item.enabled ? (ctx.isSelected ? ctx.colors.indicator : colors.text.primary) : colors.text.muted}>
        {item.enabled ? "●" : "○"}
      </span>
      <span fg={ctx.isSelected ? colors.text.primary : colors.text.secondary}> {item.label}</span>
    </text>
  );

  if (item.header) {
    return (
      <box flexDirection="column">
        <Header first={item.firstHeader}>{item.header}</Header>
        {content}
      </box>
    );
  }

  return content;
}

export function InterfaceSection({ ui, sidebar, selectedIndex, height }: InterfaceSectionProps) {
  const items = buildItems(ui, sidebar);

  let linesUsed = 0;
  let fitCount = 0;
  for (const item of items) {
    const lines = item.header ? (item.firstHeader ? 2 : 3) : 1;
    if (linesUsed + lines > height) break;
    linesUsed += lines;
    fitCount++;
  }

  return (
    <BaseSelectionList
      items={items}
      selectedIndex={selectedIndex}
      visibleLines={Math.max(1, fitCount)}
      showScrollArrows
      showIndicator={false}
      renderItem={renderItem}
      getKey={(_, i) => i}
    />
  );
}
