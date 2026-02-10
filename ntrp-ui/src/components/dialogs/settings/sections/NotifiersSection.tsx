import { Box, Text } from "ink";
import { colors, SelectionIndicator, TextInputField } from "../../../ui/index.js";
import type { UseNotifiersResult } from "../../../../hooks/useNotifiers.js";
import { TYPE_ORDER, TYPE_LABELS, TYPE_DESCRIPTIONS } from "../../../../hooks/useNotifiers.js";
import { INDICATOR_SELECTED, INDICATOR_UNSELECTED } from "../../../../lib/constants.js";

interface NotifiersSectionProps {
  notifiers: UseNotifiersResult;
  accent: string;
}

const TYPE_COLORS: Record<string, string> = {
  email: "#7AA2F7",
  telegram: "#7DCFFF",
  bash: "#9ECE6A",
};

function ListMode({ notifiers, accent }: NotifiersSectionProps) {
  const { configs, selectedIndex, testing, testResult } = notifiers;

  if (configs.length === 0) {
    return (
      <Box flexDirection="column">
        <Text color={colors.text.muted}>No notifiers configured</Text>
        <Box marginTop={1}>
          <Text color={colors.text.disabled}>a: add</Text>
        </Box>
      </Box>
    );
  }

  return (
    <Box flexDirection="column">
      {configs.map((cfg, idx) => {
        const selected = idx === selectedIndex;
        return (
          <Box key={cfg.name} flexDirection="row">
            <Box width={2} flexShrink={0}>
              <Text color={selected ? accent : colors.text.disabled}>
                {selected ? INDICATOR_SELECTED.trimEnd() : INDICATOR_UNSELECTED.trimEnd()}
              </Text>
            </Box>
            <Box width={10} flexShrink={0} marginLeft={1}>
              <Text color={TYPE_COLORS[cfg.type] ?? colors.text.secondary} bold>
                {TYPE_LABELS[cfg.type] ?? cfg.type}
              </Text>
            </Box>
            <Text color={selected ? accent : colors.text.primary}>{cfg.name}</Text>
          </Box>
        );
      })}
      {testing && (
        <Box marginTop={1}>
          <Text color={colors.status.warning}>Sending test...</Text>
        </Box>
      )}
      {!testing && testResult && (
        <Box marginTop={1}>
          <Text color={testResult.ok ? colors.status.success : colors.status.error}>
            {testResult.ok ? `✓ Sent to ${testResult.name}` : `✗ ${testResult.error}`}
          </Text>
        </Box>
      )}
      <Box marginTop={testing || testResult ? 0 : 1}>
        <Text color={colors.text.disabled}>a: add  e: edit  t: test  d: delete</Text>
      </Box>
    </Box>
  );
}

function AddTypeMode({ notifiers, accent }: NotifiersSectionProps) {
  const { typeSelectIndex } = notifiers;

  return (
    <Box flexDirection="column">
      {TYPE_ORDER.map((type, idx) => {
        const selected = idx === typeSelectIndex;
        return (
          <Box key={type} flexDirection="row">
            <SelectionIndicator selected={selected} accent={accent} />
            <Box width={12} flexShrink={0}>
              <Text color={selected ? accent : colors.text.primary} bold={selected}>
                {TYPE_LABELS[type]}
              </Text>
            </Box>
            <Text color={colors.text.muted}>{TYPE_DESCRIPTIONS[type]}</Text>
          </Box>
        );
      })}
      <Box marginTop={1}>
        <Text color={colors.text.disabled}>Enter: select  Esc: cancel</Text>
      </Box>
    </Box>
  );
}

function FormMode({ notifiers, accent }: NotifiersSectionProps) {
  const { form, formType, activeField, error, mode } = notifiers;
  const isEdit = mode === "edit-form";
  const title = `${isEdit ? "EDIT" : "ADD"} ${TYPE_LABELS[formType]?.toUpperCase()} NOTIFIER`;

  const fields: Array<{ label: string; content: React.ReactNode }> = [];

  // Name field (non-editable in edit mode)
  if (isEdit) {
    fields.push({
      label: "Name",
      content: <Text color={colors.text.muted}>{form.name}</Text>,
    });
  } else {
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
  }

  if (formType === "email") {
    const accounts = notifiers.types.email?.accounts ?? [];
    fields.push({
      label: "From",
      content: (
        <Text color={activeField === 1 ? accent : colors.text.primary}>
          {form.fromAccount || (accounts.length > 0 ? accounts[0] : "no accounts")}
          {activeField === 1 && accounts.length > 1 ? "  ◂▸" : ""}
        </Text>
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

  // In edit mode, field indices shift (name is not editable, so field 0 = first editable)
  const editOffset = isEdit ? 1 : 0;

  return (
    <Box flexDirection="column">
      <Text color={accent} bold>{title}</Text>
      <Box flexDirection="column" marginTop={1}>
        {fields.map((field, idx) => {
          const isActive = isEdit ? idx === activeField + editOffset : idx === activeField;
          return (
            <Box key={field.label} flexDirection="row">
              <Box width={2} flexShrink={0}>
                <Text color={isActive ? accent : colors.text.disabled}>
                  {isActive ? "›" : " "}
                </Text>
              </Box>
              <Box width={6} flexShrink={0}>
                <Text color={colors.text.secondary}>{field.label}</Text>
              </Box>
              {field.content}
            </Box>
          );
        })}
      </Box>
      {error && (
        <Box marginTop={1}>
          <Text color={colors.status.error}>{error}</Text>
        </Box>
      )}
      <Box marginTop={1}>
        <Text color={colors.text.disabled}>↑↓: field  Enter: next/save  Ctrl+S: save  Esc: cancel</Text>
      </Box>
    </Box>
  );
}

function ConfirmDeleteMode({ notifiers, accent }: NotifiersSectionProps) {
  const cfg = notifiers.configs[notifiers.selectedIndex];
  if (!cfg) return null;

  return (
    <Box flexDirection="column">
      <Text color={colors.status.warning}>
        Delete notifier <Text bold color={accent}>{cfg.name}</Text>?
      </Text>
      <Box marginTop={1}>
        <Text color={colors.text.disabled}>y: confirm  n/Esc: cancel</Text>
      </Box>
    </Box>
  );
}

export function NotifiersSection(props: NotifiersSectionProps) {
  const { mode, loading } = props.notifiers;

  if (loading) {
    return <Text color={colors.text.muted}>Loading...</Text>;
  }

  if (mode === "list") return <ListMode {...props} />;
  if (mode === "add-type") return <AddTypeMode {...props} />;
  if (mode === "add-form" || mode === "edit-form") return <FormMode {...props} />;
  if (mode === "confirm-delete") return <ConfirmDeleteMode {...props} />;
  return null;
}
