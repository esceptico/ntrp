import type React from "react";
import { colors, SelectionIndicator, TextInputField, Hints } from "../../../ui/index.js";
import type { UseNotifiersResult } from "../../../../hooks/useNotifiers.js";
import { TYPE_ORDER, TYPE_LABELS, TYPE_DESCRIPTIONS } from "../../../../hooks/useNotifiers.js";
import { INDICATOR_SELECTED, INDICATOR_UNSELECTED } from "../../../../lib/constants.js";

interface NotifiersSectionProps {
  notifiers: UseNotifiersResult;
  accent: string;
}

const TYPE_COLOR = colors.text.secondary;

function ListMode({ notifiers, accent }: NotifiersSectionProps) {
  const { configs, selectedIndex, testing, testResult } = notifiers;

  if (configs.length === 0) {
    return (
      <box flexDirection="column">
        <text><span fg={colors.text.muted}>No notifiers configured</span></text>
        <box marginTop={1}>
          <Hints items={[["a", "add"]]} />
        </box>
      </box>
    );
  }

  return (
    <box flexDirection="column">
      {configs.map((cfg, idx) => {
        const selected = idx === selectedIndex;
        return (
          <box key={cfg.name} flexDirection="row">
            <box width={2} flexShrink={0}>
              <text>
                <span fg={selected ? accent : colors.text.disabled}>
                  {selected ? INDICATOR_SELECTED.trimEnd() : INDICATOR_UNSELECTED.trimEnd()}
                </span>
              </text>
            </box>
            <box width={10} flexShrink={0} marginLeft={1}>
              <text>
                <span fg={TYPE_COLOR}><strong>{TYPE_LABELS[cfg.type] ?? cfg.type}</strong></span>
              </text>
            </box>
            <text><span fg={selected ? accent : colors.text.primary}>{cfg.name}</span></text>
          </box>
        );
      })}
      {testing && (
        <box marginTop={1}>
          <text><span fg={colors.status.warning}>Sending test...</span></text>
        </box>
      )}
      {!testing && testResult && (
        <box marginTop={1}>
          <text>
            <span fg={testResult.ok ? colors.status.success : colors.status.error}>
              {testResult.ok ? `✓ Sent to ${testResult.name}` : `✗ ${testResult.error}`}
            </span>
          </text>
        </box>
      )}
      <box marginTop={testing || testResult ? 0 : 1}>
        <Hints items={[["a", "add"], ["e", "edit"], ["t", "test"], ["d", "delete"]]} />
      </box>
    </box>
  );
}

function AddTypeMode({ notifiers, accent }: NotifiersSectionProps) {
  const { typeSelectIndex } = notifiers;

  return (
    <box flexDirection="column">
      {TYPE_ORDER.map((type, idx) => {
        const selected = idx === typeSelectIndex;
        return (
          <box key={type} flexDirection="row">
            <text><SelectionIndicator selected={selected} accent={accent} /></text>
            <box width={12} flexShrink={0}>
              <text>
                {selected ? (
                  <span fg={accent}><strong>{TYPE_LABELS[type]}</strong></span>
                ) : (
                  <span fg={colors.text.primary}>{TYPE_LABELS[type]}</span>
                )}
              </text>
            </box>
            <text><span fg={colors.text.muted}>{TYPE_DESCRIPTIONS[type]}</span></text>
          </box>
        );
      })}
      <box marginTop={1}>
        <Hints items={[["enter", "select"], ["esc", "cancel"]]} />
      </box>
    </box>
  );
}

function FormMode({ notifiers, accent }: NotifiersSectionProps) {
  const { form, formType, activeField, error, mode } = notifiers;
  const isEdit = mode === "edit-form";
  const title = `${isEdit ? "EDIT" : "ADD"} ${TYPE_LABELS[formType]?.toUpperCase()} NOTIFIER`;

  const fields: Array<{ label: string; content: React.ReactNode }> = [];

  fields.push({
    label: "Name",
    content: (
      <TextInputField
        value={form.name}
        cursorPos={form.nameCursor}
        placeholder="notifier-name"
        showCursor={activeField === 0}
      />
    ),
  });

  if (formType === "email") {
    const accounts = notifiers.types.email?.accounts ?? [];
    const fromActive = activeField === 1;
    fields.push({
      label: "From",
      content: (
        <text>
          <span fg={fromActive ? accent : colors.text.primary}>
            {form.fromAccount || (accounts.length > 0 ? accounts[0] : "no accounts")}
            {fromActive && accounts.length > 1 ? "  ◂▸" : ""}
          </span>
        </text>
      ),
    });
    fields.push({
      label: "To",
      content: (
        <TextInputField
          value={form.toAddress}
          cursorPos={form.toAddressCursor}
          placeholder="recipient@example.com"
          showCursor={activeField === 2}
        />
      ),
    });
  } else if (formType === "telegram") {
    fields.push({
      label: "User",
      content: (
        <TextInputField
          value={form.userId}
          cursorPos={form.userIdCursor}
          placeholder="Telegram chat/user ID"
          showCursor={activeField === 1}
        />
      ),
    });
  } else {
    fields.push({
      label: "Cmd",
      content: (
        <TextInputField
          value={form.command}
          cursorPos={form.commandCursor}
          placeholder="ntfy publish topic"
          showCursor={activeField === 1}
        />
      ),
    });
  }

  return (
    <box flexDirection="column">
      <text><span fg={accent}><strong>{title}</strong></span></text>
      <box flexDirection="column" marginTop={1}>
        {fields.map((field, idx) => {
          const isActive = idx === activeField;
          return (
            <box key={field.label} flexDirection="row">
              <box width={2} flexShrink={0}>
                <text>
                  <span fg={isActive ? accent : colors.text.disabled}>
                    {isActive ? "›" : " "}
                  </span>
                </text>
              </box>
              <box width={6} flexShrink={0}>
                <text><span fg={colors.text.secondary}>{field.label}</span></text>
              </box>
              {field.content}
            </box>
          );
        })}
      </box>
      {error && (
        <box marginTop={1}>
          <text><span fg={colors.status.error}>{error}</span></text>
        </box>
      )}
      <box marginTop={1}>
        <Hints items={[["↑↓", "field"], ["enter", "next/save"], ["ctrl+s", "save"], ["esc", "cancel"]]} />
      </box>
    </box>
  );
}

function ConfirmDeleteMode({ notifiers, accent }: NotifiersSectionProps) {
  const cfg = notifiers.configs[notifiers.selectedIndex];
  if (!cfg) return null;

  return (
    <box flexDirection="column">
      <text>
        <span fg={colors.status.warning}>Delete notifier </span>
        <span fg={accent}><strong>{cfg.name}</strong></span>
        <span fg={colors.status.warning}>?</span>
      </text>
      <box marginTop={1}>
        <Hints items={[["y", "confirm"], ["n/esc", "cancel"]]} />
      </box>
    </box>
  );
}

export function NotifiersSection(props: NotifiersSectionProps) {
  const { mode, loading } = props.notifiers;

  if (loading) {
    return <text><span fg={colors.text.muted}>Loading...</span></text>;
  }

  if (mode === "list") return <ListMode {...props} />;
  if (mode === "add-type") return <AddTypeMode {...props} />;
  if (mode === "add-form" || mode === "edit-form") return <FormMode {...props} />;
  if (mode === "confirm-delete") return <ConfirmDeleteMode {...props} />;
  return null;
}
