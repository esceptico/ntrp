import { useState, useEffect, useCallback } from "react";
import { Dialog, colors, Hints, SelectionIndicator, SelectList, type SelectOption } from "../ui/index.js";
import {
  getSupportedModels,
  getEmbeddingModels,
  updateConfig,
  updateEmbeddingModel,
  getServerConfig,
  type ServerConfig,
  type ModelGroup,
} from "../../api/client.js";
import { useKeypress, useAccentColor, type Key } from "../../hooks/index.js";
import type { Config } from "../../types.js";

type ModelType = "chat" | "research" | "memory" | "embedding";

const PROVIDER_LABELS: Record<string, string> = {
  anthropic: "Anthropic",
  claude_oauth: "Claude Pro/Max",
  openai: "OpenAI",
  google: "Google",
  openrouter: "OpenRouter",
  custom: "Custom",
};

function stripOAuthPrefix(model: string): string {
  return model.startsWith("oauth:") ? model.slice(6) : model;
}

function buildModelOptions(modelList: string[], groups: ModelGroup[], currentModel: string): SelectOption[] {
  if (groups.length > 0) {
    return groups.flatMap(g =>
      g.models.map(m => ({
        value: m,
        title: stripOAuthPrefix(m),
        category: PROVIDER_LABELS[g.provider] || g.provider,
        indicator: m === currentModel ? "●" : undefined,
      }))
    );
  }
  return modelList.map(m => ({
    value: m,
    title: stripOAuthPrefix(m),
    indicator: m === currentModel ? "●" : undefined,
  }));
}

const MODEL_TYPES: { type: ModelType; label: string; description: string }[] = [
  { type: "chat", label: "Agent", description: "Main conversation model" },
  { type: "research", label: "Research", description: "Research agent model" },
  { type: "memory", label: "Memory", description: "Fact extraction & consolidation" },
  { type: "embedding", label: "Embedding", description: "Vector embeddings for search" },
];

interface ModelPickerProps {
  config: Config;
  serverConfig: ServerConfig | null;
  onModelChange: (type: ModelType, model: string) => void;
  onServerConfigChange: (config: ServerConfig) => void;
  onRefreshIndexStatus: () => Promise<void>;
  onClose: () => void;
}

export function ModelPicker({ config, serverConfig, onModelChange, onServerConfigChange, onRefreshIndexStatus, onClose }: ModelPickerProps) {
  const { accentValue } = useAccentColor();
  const [step, setStep] = useState<"type" | "model" | "confirm-reindex">("type");
  const [typeIndex, setTypeIndex] = useState(0);
  const [selectedType, setSelectedType] = useState<ModelType>("chat");

  const [models, setModels] = useState<string[]>([]);
  const [modelGroups, setModelGroups] = useState<ModelGroup[]>([]);
  const [embeddingModels, setEmbeddingModels] = useState<string[]>([]);
  const [embeddingGroups, setEmbeddingGroups] = useState<ModelGroup[]>([]);
  const [saving, setSaving] = useState(false);

  const [pendingEmbedding, setPendingEmbedding] = useState<string | null>(null);
  const [reindexing, setReindexing] = useState(false);
  const [localOverrides, setLocalOverrides] = useState<Partial<Record<ModelType, string>>>({});

  const currentModels: Record<ModelType, string> = {
    chat: localOverrides.chat ?? serverConfig?.chat_model ?? "",
    research: localOverrides.research ?? serverConfig?.research_model ?? "",
    memory: localOverrides.memory ?? serverConfig?.memory_model ?? "",
    embedding: localOverrides.embedding ?? serverConfig?.embedding_model ?? "",
  };

  useEffect(() => {
    getSupportedModels(config)
      .then((result) => { setModels(result.models); setModelGroups(result.groups); })
      .catch(() => {});
    getEmbeddingModels(config)
      .then((result) => { setEmbeddingModels(result.models); setEmbeddingGroups(result.groups); })
      .catch(() => {});
  }, [config]);

  const handleSelectModelType = useCallback(() => {
    const t = MODEL_TYPES[typeIndex];
    setSelectedType(t.type);
    setStep("model");
  }, [typeIndex]);

  const handleModelSelect = useCallback(async (model: string) => {
    if (saving) return;

    if (selectedType === "embedding") {
      if (model === currentModels.embedding) {
        setStep("type");
        return;
      }
      setPendingEmbedding(model);
      setStep("confirm-reindex");
      return;
    }

    const currentModel = currentModels[selectedType];
    if (model === currentModel) {
      setStep("type");
      return;
    }

    setSaving(true);
    try {
      const key = `${selectedType}_model`;
      await updateConfig(config, { [key]: model } as Record<string, string>);
      setLocalOverrides(prev => ({ ...prev, [selectedType]: model }));
      onModelChange(selectedType, model);
      setStep("type");
    } catch {
    } finally {
      setSaving(false);
    }
  }, [config, selectedType, currentModels, saving, onModelChange]);

  const handleConfirmReindex = useCallback(async () => {
    if (!pendingEmbedding || reindexing) return;
    setReindexing(true);
    try {
      const result = await updateEmbeddingModel(config, pendingEmbedding);
      if (result.status === "reindexing") {
        const updatedConfig = await getServerConfig(config);
        onServerConfigChange(updatedConfig);
        onModelChange("embedding", pendingEmbedding);
        await onRefreshIndexStatus();
      }
      onClose();
    } catch {
    } finally {
      setReindexing(false);
    }
  }, [config, pendingEmbedding, reindexing, onServerConfigChange, onModelChange, onRefreshIndexStatus, onClose]);

  // Type selection keypress
  const handleTypeKeypress = useCallback((key: Key) => {
    if (key.name === "escape") { onClose(); return; }
    if (key.name === "up" || key.name === "k") {
      setTypeIndex(i => Math.max(0, i - 1));
    } else if (key.name === "down" || key.name === "j") {
      setTypeIndex(i => Math.min(MODEL_TYPES.length - 1, i + 1));
    } else if (key.name === "return" || key.name === "space") {
      handleSelectModelType();
    }
  }, [onClose, handleSelectModelType]);

  // Reindex confirmation keypress
  const handleReindexKeypress = useCallback((key: Key) => {
    if (key.name === "escape" || key.sequence === "n") {
      setPendingEmbedding(null);
      setStep("model");
    } else if (key.name === "return" || key.sequence === "y") {
      handleConfirmReindex();
    }
  }, [handleConfirmReindex]);

  useKeypress(handleTypeKeypress, { isActive: step === "type" });
  useKeypress(handleReindexKeypress, { isActive: step === "confirm-reindex" && !reindexing });

  if (step === "confirm-reindex") {
    return (
      <Dialog title="CONFIRM RE-INDEX" size="medium" onClose={() => { setPendingEmbedding(null); setStep("model"); }}>
        {() => (
          <box flexDirection="column">
            <text><span fg={colors.text.primary}>Change embedding model to:</span></text>
            <text><span fg={accentValue}><strong> {pendingEmbedding}</strong></span></text>
            <box marginTop={1}>
              <text><span fg={colors.status.warning}>This will clear the search index and re-embed all content.</span></text>
            </box>
            {reindexing ? (
              <box marginTop={1}>
                <text><span fg={colors.text.muted}>Re-indexing...</span></text>
              </box>
            ) : (
              <box marginTop={1}>
                <Hints items={[["y", "confirm"], ["n/esc", "cancel"]]} />
              </box>
            )}
          </box>
        )}
      </Dialog>
    );
  }

  if (step === "model") {
    const isEmbedding = selectedType === "embedding";
    const modelList = isEmbedding ? embeddingModels : models;
    const groups = isEmbedding ? embeddingGroups : modelGroups;
    const title = MODEL_TYPES.find(t => t.type === selectedType)?.label ?? "Model";

    if (modelList.length === 0) {
      return (
        <Dialog title={`${title.toUpperCase()} MODEL`} size="medium" onClose={() => setStep("type")}>
          {() => <text><span fg={colors.text.muted}>Loading models...</span></text>}
        </Dialog>
      );
    }

    const modelOptions = buildModelOptions(modelList, groups, currentModels[selectedType]);
    const currentIdx = modelOptions.findIndex(o => o.value === currentModels[selectedType]);

    return (
      <Dialog title={`${title.toUpperCase()} MODEL`} size="medium" onClose={() => setStep("type")}>
        {({ width, height }) => (
          <SelectList
            options={modelOptions}
            search
            initialIndex={Math.max(0, currentIdx)}
            visibleLines={height}
            width={width}
            onSelect={(opt) => handleModelSelect(opt.value)}
            onClose={() => setStep("type")}
          />
        )}
      </Dialog>
    );
  }

  // Step: type selection
  return (
    <Dialog title="MODELS" size="medium" onClose={onClose}>
      {() => (
        <box flexDirection="column">
          {MODEL_TYPES.map((mt, i) => {
            const selected = i === typeIndex;
            const rawModel = stripOAuthPrefix(currentModels[mt.type]);
            const shortName = rawModel.split("/").pop() || rawModel || "—";
            return (
              <box key={mt.type} flexDirection="row">
                <text>
                  <SelectionIndicator selected={selected} accent={accentValue} />
                  <span fg={selected ? colors.text.primary : colors.text.secondary}>{mt.label.padEnd(14)}</span>
                  <span fg={selected ? accentValue : colors.text.muted}>{shortName}</span>
                </text>
              </box>
            );
          })}
          <box marginTop={1}>
            {MODEL_TYPES[typeIndex] && (
              <text><span fg={colors.text.disabled}>{MODEL_TYPES[typeIndex].description}</span></text>
            )}
          </box>
          <box marginTop={1}>
            <Hints items={[["↑↓", "move"], ["enter", "select"], ["esc", "close"]]} />
          </box>
        </box>
      )}
    </Dialog>
  );
}
