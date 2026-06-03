import type { ReactNode } from "react";
import { LabeledField } from "../Field";
import { KeyValueEditor, ListEditor, type KeyVal } from "./editors";
import { SegmentedControl } from "../../SegmentedControl";
import type { MCPAuthMode } from "./payload";

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
      <LabeledField label="Command to launch">
        <input
          type="text"
          value={command}
          onChange={(e) => onCommand(e.target.value)}
          placeholder="openai-dev-mcp serve-sqlite"
          spellCheck={false}
          className="w-full h-8 px-2.5 rounded-md border border-line-soft bg-surface text-base text-ink outline-none focus:border-line transition-colors font-mono"
        />
      </LabeledField>

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
      <LabeledField label="URL">
        <input
          type="text"
          value={url}
          onChange={(e) => onUrl(e.target.value)}
          placeholder="https://mcp.example.com/mcp"
          spellCheck={false}
          className="w-full h-8 px-2.5 rounded-md border border-line-soft bg-surface text-base text-ink outline-none focus:border-line transition-colors font-mono"
        />
      </LabeledField>

      {oauthSection ?? (
        <>
          <LabeledField label="Auth">
            <SegmentedControl
              className="justify-self-start"
              size="sm"
              value={auth}
              onChange={(v) => onAuth(v as MCPAuthMode)}
              options={[
                { value: "auto", label: "Auto" },
                { value: "headers", label: "Headers" },
              ]}
            />
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
                <p className="mt-1.5 m-0 text-xs text-faint">
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
