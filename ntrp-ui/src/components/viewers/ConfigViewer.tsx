import React, { useState, useEffect, useCallback } from "react";
import { Box, Text } from "ink";
import type { Config } from "../../types.js";
import { getServerConfig, getStats, updateModels, type ServerConfig, type Stats } from "../../api/client.js";
import { useKeypress, type Key } from "../../hooks/useKeypress.js";
import { useDimensions } from "../../contexts/index.js";
import {
  Panel,
  Divider,
  Footer,
  Section,
  KeyValue,
  Loading,
  ErrorDisplay,
  colors,
  brand,
  truncateText,
} from "../ui/index.js";

const MODELS = ["google/gemini-3-flash-preview", "anthropic/claude-sonnet-4.5"];

interface ConfigViewerProps {
  config: Config;
  onClose: () => void;
}

export function ConfigViewer({ config, onClose }: ConfigViewerProps) {
  const { width: terminalWidth } = useDimensions();
  const [serverConfig, setServerConfig] = useState<ServerConfig | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [updateError, setUpdateError] = useState<string | null>(null);
  const [isFocused, setIsFocused] = useState(false);
  const [updating, setUpdating] = useState(false);

  const contentWidth = Math.max(0, terminalWidth - 4);
  const valueWidth = Math.max(0, contentWidth - 20);

  useEffect(() => {
    async function loadData() {
      setLoading(true);
      try {
        const [cfg, st] = await Promise.all([
          getServerConfig(config),
          getStats(config),
        ]);
        setServerConfig(cfg);
        setStats(st);
      } catch (e) {
        setLoadError(`Failed to load: ${e}`);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [config]);

  const getModels = useCallback(() => {
    if (!serverConfig) return MODELS;
    const current = serverConfig.chat_model;
    if (MODELS.includes(current)) return MODELS;
    return [current, ...MODELS];
  }, [serverConfig]);

  const cycleModel = useCallback(async (direction: 1 | -1) => {
    if (!serverConfig || updating) return;

    const models = getModels();
    const current = serverConfig.chat_model;
    const currentIdx = models.indexOf(current);
    const nextIdx = (currentIdx + direction + models.length) % models.length;
    const nextModel = models[nextIdx];

    if (nextModel === current) return;

    setUpdating(true);
    try {
      const updated = await updateModels(config, { chat_model: nextModel });
      setServerConfig(prev => prev ? { ...prev, ...updated } : prev);
    } catch (e) {
      setUpdateError(`Failed to update: ${e}`);
      setTimeout(() => setUpdateError(null), 2000);
    } finally {
      setUpdating(false);
    }
  }, [config, serverConfig, updating, getModels]);

  const handleKeypress = useCallback(
    (key: Key) => {
      if (key.name === "escape" || key.name === "q") {
        if (isFocused) {
          setIsFocused(false);
        } else {
          onClose();
        }
        return;
      }

      if (key.name === "tab" || key.name === "return") {
        setIsFocused(f => !f);
        return;
      }

      if (isFocused && (key.name === "left" || key.name === "right")) {
        cycleModel(key.name === "right" ? 1 : -1);
        return;
      }
    },
    [onClose, isFocused, cycleModel]
  );

  useKeypress(handleKeypress, { isActive: true });

  if (loading) {
    return <Loading message="Loading config..." />;
  }

  if (loadError || !serverConfig || !stats) {
    return <ErrorDisplay message={loadError || "Failed to load config"} />;
  }

  const models = getModels();
  const idx = models.indexOf(serverConfig.chat_model);
  const hasLeft = idx > 0;
  const hasRight = idx < models.length - 1;

  return (
    <Panel title="CONFIGURATION" width={contentWidth}>
      <Divider width={contentWidth - 2} />

      {/* Models section */}
      <Section title="Models">
        <KeyValue
          label="  Model"
          labelWidth={18}
          value={
            isFocused ? (
              <Text>
                <Text color={hasLeft ? colors.text.secondary : colors.text.disabled}>{"◀ "}</Text>
                <Text color={brand.primary} bold inverse={updating}>
                  {` ${truncateText(serverConfig.chat_model, valueWidth - 6)} `}
                </Text>
                <Text color={hasRight ? colors.text.secondary : colors.text.disabled}>{" ▶"}</Text>
              </Text>
            ) : (
              truncateText(serverConfig.chat_model, valueWidth)
            )
          }
        />
        <KeyValue label="  Embedding" labelWidth={18} value={truncateText(serverConfig.embedding_model, valueWidth)} />
      </Section>

      {/* Sources section */}
      <Section title="Sources">
        <KeyValue label="  Vault" labelWidth={18} value={truncateText(serverConfig.vault_path || "(not set)", valueWidth)} />
        <KeyValue
          label="  Browser"
          labelWidth={18}
          value={serverConfig.has_browser ? `✓ ${serverConfig.browser}` : "✗ not available"}
          valueColor={serverConfig.has_browser ? brand.primary : colors.text.secondary}
        />
        <KeyValue
          label="  Gmail"
          labelWidth={18}
          value={serverConfig.has_gmail
            ? `✓ connected (${serverConfig.gmail_accounts.length})`
            : "✗ not available"}
          valueColor={serverConfig.has_gmail ? brand.primary : colors.text.secondary}
        />
        {serverConfig.has_gmail && serverConfig.gmail_accounts.length > 0 && (
          <Box flexDirection="column">
            {serverConfig.gmail_accounts.map((email) => (
              <KeyValue key={email} label="" labelWidth={18} value={truncateText(email, valueWidth)} />
            ))}
          </Box>
        )}
      </Section>

      {/* Agent section */}
      <Section title="Agent">
        <KeyValue label="  Max Depth" labelWidth={18} value={String(serverConfig.max_depth)} />
      </Section>

      {/* Stats section */}
      <Section title="Stats">
        <KeyValue label="  Facts" labelWidth={18} value={String(stats.fact_count)} />
        <KeyValue label="  Links" labelWidth={18} value={String(stats.link_count)} />
      </Section>

      <Divider width={contentWidth - 2} />

      {updateError && (
        <Box marginBottom={1}>
          <Text color={colors.status.error}>{updateError}</Text>
        </Box>
      )}

      <Footer>Tab: select model │ ←→: change │ Esc: close</Footer>
    </Panel>
  );
}
