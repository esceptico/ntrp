import { useState } from "react";
import { useStore } from "../../store";
import { updateServerConfig, fetchServerConfig } from "../../actions";
import type { ModelGroup } from "../../api";
import { ModelReasoningPicker } from "../ComposerSelectors";
import { SettingsConnectionHint, SettingsInlineError } from "./SettingsNotice";

type ModelKind = "research_model" | "memory_model";

const KIND_LABELS: Record<ModelKind, { title: string; description: string }> = {
  research_model: {
    title: "Research",
    description: "Used by research-style sub-agents and deeper investigations.",
  },
  memory_model: {
    title: "Memory",
    description: "Fact extraction and pattern consolidation.",
  },
};

const SETTINGS_MODEL_KINDS: ModelKind[] = ["research_model", "memory_model"];

export function ModelsTab() {
  const connected = useStore((s) => s.connected);
  const cfg = useStore((s) => s.serverConfig);
  const models = useStore((s) => s.serverModels);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!cfg) {
    if (!connected) return <SettingsConnectionHint />;
    return <div className="text-sm text-faint">Loading models…</div>;
  }

  if (!models) {
    return (
      <div className="grid gap-3">
        <SettingsInlineError
          title="Couldn't load models"
          message="The server is reachable, but the model list did not load."
        />
        <SettingsConnectionHint
          title="Check provider setup"
          detail="Connect at least one model provider in Providers, then refresh this view."
        />
      </div>
    );
  }

  if (
    !Object.prototype.hasOwnProperty.call(cfg, "model_reasoning_efforts") ||
    !Object.prototype.hasOwnProperty.call(models, "reasoning_efforts")
  ) {
    return (
      <SettingsInlineError
        title="Model settings contract changed"
        message="The desktop UI and server model metadata are out of sync. Restart the server, then reopen Settings."
      />
    );
  }

  const groups: ModelGroup[] = models.groups.length > 0
    ? models.groups
    : [{ provider: "all", models: models.models }];

  return (
    <div className="grid gap-5">
      <div className="rounded-[10px] border border-line-soft bg-surface-soft/45 px-3.5 py-3 text-sm leading-[1.45] text-muted">
        The chat model and reasoning level live in the composer. These defaults are for background work.
      </div>

      <div className="grid divide-y divide-line-soft">
        {SETTINGS_MODEL_KINDS.map((kind) => {
          const current = cfg[kind];
          const meta = KIND_LABELS[kind];
          return (
            <Section
              key={kind}
              title={meta.title}
              description={meta.description}
              current={current}
              savingModel={saving === `${kind}:model`}
              savingReasoning={saving === `${kind}:reasoning`}
              groups={groups}
              reasoningEfforts={models.reasoning_efforts}
              currentReasoning={cfg.model_reasoning_efforts[current] ?? null}
              onSelect={async (model) => {
                if (model === current || saving) return;
                setSaving(`${kind}:model`);
                setError(null);
                try {
                  await updateServerConfig({ [kind]: model });
                } catch (err) {
                  setError(err instanceof Error ? err.message : String(err));
                  await fetchServerConfig();
                } finally {
                  setSaving(null);
                }
              }}
              onSetReasoning={async (effort) => {
                if (saving) return;
                setSaving(`${kind}:reasoning`);
                setError(null);
                try {
                  await updateServerConfig({
                    reasoning_model: current,
                    reasoning_effort: effort,
                  });
                } catch (err) {
                  setError(err instanceof Error ? err.message : String(err));
                  await fetchServerConfig();
                } finally {
                  setSaving(null);
                }
              }}
            />
          );
        })}
      </div>
      {error && (
        <SettingsInlineError title="Couldn't update model" message={error} />
      )}
    </div>
  );
}

function Section({
  title,
  description,
  current,
  groups,
  savingModel,
  savingReasoning,
  reasoningEfforts,
  currentReasoning,
  onSelect,
  onSetReasoning,
}: {
  title: string;
  description: string;
  current: string;
  groups: ModelGroup[];
  savingModel: boolean;
  savingReasoning: boolean;
  reasoningEfforts: Record<string, string[]>;
  currentReasoning: string | null;
  onSelect: (model: string) => void;
  onSetReasoning: (effort: string | null) => void;
}) {
  const efforts = reasoningEfforts[current] ?? [];

  return (
    <div className="grid gap-2.5 py-3">
      <div className="grid gap-0.5">
        <div className="text-base font-medium text-ink">{title}</div>
        <div className="text-xs text-faint leading-[1.4]">{description}</div>
      </div>

      <ModelReasoningPicker
        buttonLabel={savingModel ? "Saving..." : undefined}
        currentModel={current}
        currentEffort={currentReasoning}
        efforts={efforts}
        groups={groups}
        disabled={savingModel || savingReasoning}
        placement="below-left"
        onSelectModel={onSelect}
        onSelectEffort={onSetReasoning}
      />
    </div>
  );
}
