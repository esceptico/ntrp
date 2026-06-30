import type { ReactNode } from "react";
import { LabeledField } from "@/components/ui/LabeledField";
import { KeyValueEditor, ListEditor, type KeyVal } from "@/features/settings/components/mcp/editors";
import { SegmentedControl, SegmentedControlItem } from "@/components/ui/SegmentedControl";
import { Input } from "@/components/ui/Input";
import type { MCPAuthMode } from "@/features/settings/components/mcp/payload";

export function StdioFields({
  command,
  onCommand,
  argsList,
  onArgs,
  envEntries,
  onEnv,
}: {
  command: string;
  onCommand: (v: string) => void;
  argsList: string[];
  onArgs: (v: string[]) => void;
  envEntries: KeyVal[];
  onEnv: (v: KeyVal[]) => void;
}) {
  return (
    <>
      <Input
        label="Command to launch"
        size="sm"
        value={command}
        onChange={(e) => onCommand(e.target.value)}
        placeholder="openai-dev-mcp serve-sqlite"
        spellCheck={false}
        className="font-mono"
      />

      <LabeledField label="Arguments">
        <ListEditor
          values={argsList}
          onChange={onArgs}
          placeholder=""
          addLabel="Add argument"
          mono
        />
      </LabeledField>

      <LabeledField label="Environment variables">
        <KeyValueEditor entries={envEntries} onChange={onEnv} addLabel="Add environment variable" />
      </LabeledField>
    </>
  );
}

export function HttpFields({
  url,
  onUrl,
  headerEntries,
  onHeaders,
  auth,
  onAuth,
  hasExistingHeaders,
  oauthSection,
}: {
  url: string;
  onUrl: (v: string) => void;
  headerEntries: KeyVal[];
  onHeaders: (v: KeyVal[]) => void;
  auth: MCPAuthMode;
  onAuth: (v: MCPAuthMode) => void;
  hasExistingHeaders?: boolean;
  oauthSection?: ReactNode;
}) {
  return (
    <>
      <Input
        label="URL"
        size="sm"
        value={url}
        onChange={(e) => onUrl(e.target.value)}
        placeholder="https://mcp.example.com/mcp"
        spellCheck={false}
        className="font-mono"
      />

      {oauthSection ?? (
        <>
          <LabeledField label="Auth">
            <SegmentedControl
              size="sm"
              value={auth}
              onChange={(v) => onAuth(v as MCPAuthMode)}
            >
              <SegmentedControlItem value="auto">Auto</SegmentedControlItem>
              <SegmentedControlItem value="headers">Headers</SegmentedControlItem>
            </SegmentedControl>
          </LabeledField>

          {auth === "headers" ? (
            <LabeledField label="Headers">
              <KeyValueEditor
                entries={headerEntries}
                onChange={onHeaders}
                addLabel="Add header"
                valuePlaceholder={hasExistingHeaders ? "•••••• unchanged" : "Value"}
              />
              {hasExistingHeaders && (
                <p className="mt-1.5 m-0 text-xs text-muted">
                  Existing values are hidden. Leave a value blank to keep it.
                </p>
              )}
            </LabeledField>
          ) : null}
        </>
      )}
    </>
  );
}
