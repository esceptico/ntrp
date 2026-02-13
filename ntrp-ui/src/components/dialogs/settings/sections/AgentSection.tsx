import { ModelSelector } from "../SettingsRows.js";

interface AgentSectionProps {
  chatModel: string;
  exploreModel: string;
  memoryModel: string;
  embeddingModel: string;
  selectedIndex: number;
  accent: string;
  modelNameWidth: number;
}

export function AgentSection({
  chatModel,
  exploreModel,
  memoryModel,
  embeddingModel,
  selectedIndex,
  accent,
  modelNameWidth,
}: AgentSectionProps) {
  return (
    <box flexDirection="column">
      <ModelSelector
        label="Agent"
        currentModel={chatModel}
        selected={selectedIndex === 0}
        accent={accent}
        maxWidth={modelNameWidth}
      />
      <ModelSelector
        label="Explore"
        currentModel={exploreModel}
        selected={selectedIndex === 1}
        accent={accent}
        maxWidth={modelNameWidth}
      />
      <ModelSelector
        label="Memory"
        currentModel={memoryModel}
        selected={selectedIndex === 2}
        accent={accent}
        maxWidth={modelNameWidth}
      />
      <ModelSelector
        label="Embedding"
        currentModel={embeddingModel}
        selected={selectedIndex === 3}
        accent={accent}
        maxWidth={modelNameWidth}
      />
    </box>
  );
}
