import { colors } from "./colors.js";

interface TabsProps<T extends string> {
  tabs: readonly T[];
  activeTab: T;
  onTabChange: (tab: T) => void;
  labels?: Record<T, string>;
}

export function Tabs<T extends string>({ tabs, activeTab, labels }: TabsProps<T>) {
  return (
    <box marginBottom={1}>
      {tabs.map((tab, i) => {
        const isActive = tab === activeTab;
        const label = labels?.[tab] || tab.charAt(0).toUpperCase() + tab.slice(1);

        return (
          <box key={tab} marginRight={1}>
            <text>
              {isActive ? (
                <span fg="#000000" bg={colors.tabs.active}><strong> {label.toUpperCase()} </strong></span>
              ) : (
                <span fg={colors.tabs.inactive}> {label.toUpperCase()} </span>
              )}
              {i < tabs.length - 1 && <span fg={colors.tabs.separator}>{"\u2502"}</span>}
            </text>
          </box>
        );
      })}
    </box>
  );
}
