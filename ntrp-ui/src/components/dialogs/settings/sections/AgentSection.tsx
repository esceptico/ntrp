import { NumberListSection } from "../SettingsRows.js";
import { AGENT_ITEMS } from "../config.js";
import type { AgentSettings } from "../../../../hooks/useSettings.js";

interface AgentSectionProps {
  settings: AgentSettings;
  selectedIndex: number;
  accent: string;
}

export function AgentSection({ settings, selectedIndex, accent }: AgentSectionProps) {
  return <NumberListSection items={AGENT_ITEMS} settings={settings} selectedIndex={selectedIndex} accent={accent} />;
}
