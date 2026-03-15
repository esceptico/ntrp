import { NumberListSection } from "../SettingsRows.js";
import { CONTEXT_ITEMS } from "../config.js";
import type { AgentSettings } from "../../../../hooks/useSettings.js";

interface ContextSectionProps {
  settings: AgentSettings;
  selectedIndex: number;
  accent: string;
}

export function ContextSection({ settings, selectedIndex, accent }: ContextSectionProps) {
  return <NumberListSection items={CONTEXT_ITEMS} settings={settings} selectedIndex={selectedIndex} accent={accent} />;
}
