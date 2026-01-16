import React, { useState, useEffect, useCallback } from "react";
import { Box, Text } from "ink";
import type { Config } from "../../../types.js";
import { getGmailAccounts, addGmailAccount, removeGmailAccount, getServerConfig, type GmailAccount, type ServerConfig } from "../../../api/client.js";
import { useKeypress, type Key } from "../../../hooks/useKeypress.js";
import { useDimensions } from "../../../contexts/index.js";
import { Panel, Tabs, Divider, Footer, Loading, colors } from "../../ui/index.js";
import { VaultSection } from "./VaultSection.js";
import { GmailSection } from "./GmailSection.js";
import { BrowserSection } from "./BrowserSection.js";

type Section = "vault" | "gmail" | "browser";

interface ConnectionsViewerProps {
  config: Config;
  onClose: () => void;
  onStatusMessage: (msg: string) => void;
}

export function ConnectionsViewer({ config, onClose, onStatusMessage }: ConnectionsViewerProps) {
  const { width: terminalWidth } = useDimensions();
  const [serverConfig, setServerConfig] = useState<ServerConfig | null>(null);
  const [gmailAccounts, setGmailAccounts] = useState<GmailAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState<Section>("vault");
  const [selectedGmailIndex, setSelectedGmailIndex] = useState(0);
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);

  const sections: Section[] = ["vault", "gmail", "browser"];
  const contentWidth = Math.max(0, terminalWidth - 4);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [cfg, gmail] = await Promise.all([
        getServerConfig(config),
        getGmailAccounts(config),
      ]);
      setServerConfig(cfg);
      setGmailAccounts(gmail.accounts);
    } catch (e) {
      setError(`Failed to load: ${e}`);
    } finally {
      setLoading(false);
    }
  }, [config]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleAddGmail = useCallback(async () => {
    setActionInProgress("Adding Gmail (check browser)...");
    try {
      const result = await addGmailAccount(config);
      onStatusMessage(`✓ Connected: ${result.email}`);
      await loadData();
    } catch (e) {
      onStatusMessage(`✗ Failed: ${e}`);
    } finally {
      setActionInProgress(null);
    }
  }, [config, loadData, onStatusMessage]);

  const handleRemoveGmail = useCallback(async () => {
    const account = gmailAccounts[selectedGmailIndex];
    if (!account) return;

    setActionInProgress(`Removing ${account.email || account.token_file}...`);
    try {
      const result = await removeGmailAccount(config, account.token_file);
      onStatusMessage(`✓ Removed: ${result.email || account.token_file}`);
      await loadData();
      setSelectedGmailIndex(Math.max(0, selectedGmailIndex - 1));
    } catch (e) {
      onStatusMessage(`✗ Failed: ${e}`);
    } finally {
      setActionInProgress(null);
    }
  }, [config, gmailAccounts, selectedGmailIndex, loadData, onStatusMessage]);

  const handleKeypress = useCallback(
    (key: Key) => {
      if (actionInProgress) return;

      if (key.name === "escape" || key.name === "q") {
        onClose();
        return;
      }

      if (key.name === "tab" || key.name === "right") {
        const idx = sections.indexOf(activeSection);
        setActiveSection(sections[(idx + 1) % sections.length]);
        return;
      }
      if (key.name === "left") {
        const idx = sections.indexOf(activeSection);
        setActiveSection(sections[(idx - 1 + sections.length) % sections.length]);
        return;
      }

      if (activeSection === "gmail") {
        if (key.name === "up") {
          setSelectedGmailIndex((i) => Math.max(0, i - 1));
          return;
        }
        if (key.name === "down") {
          setSelectedGmailIndex((i) => Math.min(gmailAccounts.length - 1, i + 1));
          return;
        }
        if (key.name === "a") {
          handleAddGmail();
          return;
        }
        if ((key.name === "d" || key.name === "delete") && gmailAccounts.length > 0) {
          handleRemoveGmail();
          return;
        }
      }
    },
    [onClose, activeSection, sections, gmailAccounts.length, handleAddGmail, handleRemoveGmail, actionInProgress]
  );

  useKeypress(handleKeypress, { isActive: true });

  if (loading) {
    return <Loading message="Loading connections..." />;
  }

  return (
    <Panel title="CONNECTIONS" width={contentWidth}>
      <Tabs
        tabs={sections}
        activeTab={activeSection}
        onTabChange={setActiveSection}
        labels={{ vault: "Vault", gmail: "Gmail", browser: "Browser" }}
      />

      <Divider width={contentWidth - 2} />

      {error && (
        <Box marginY={1}>
          <Text color={colors.status.error}>{error}</Text>
        </Box>
      )}

      {activeSection === "vault" && serverConfig && (
        <VaultSection serverConfig={serverConfig} width={contentWidth} />
      )}

      {activeSection === "gmail" && (
        <GmailSection
          accounts={gmailAccounts}
          selectedIndex={selectedGmailIndex}
          width={contentWidth}
        />
      )}

      {activeSection === "browser" && serverConfig && (
        <BrowserSection serverConfig={serverConfig} width={contentWidth} />
      )}

      <Divider width={contentWidth - 2} />

      {actionInProgress && (
        <Box marginTop={1}>
          <Text color={colors.status.warning}>{actionInProgress}</Text>
        </Box>
      )}

      <Footer>
        {activeSection === "gmail"
          ? "a: add │ d: remove │ ←→/Tab: section │ Esc: close"
          : "←→/Tab: section │ Esc: close"
        }
      </Footer>
    </Panel>
  );
}
