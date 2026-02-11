import { Box, Text } from "ink";
import { colors, TextInputField } from "../../../ui/index.js";
import type { UseSkillsResult } from "../../../../hooks/useSkills.js";
import { INDICATOR_SELECTED, INDICATOR_UNSELECTED } from "../../../../lib/constants.js";

interface SkillsSectionProps {
  skills: UseSkillsResult;
  accent: string;
}

const LOCATION_COLORS: Record<string, string> = {
  project: "#7AA2F7",
  global: "#9ECE6A",
};

function ListMode({ skills: s, accent }: SkillsSectionProps) {
  if (s.skills.length === 0) {
    return (
      <Box flexDirection="column">
        <Text color={colors.text.muted}>No skills installed</Text>
        <Box marginTop={1}>
          <Text color={colors.text.disabled}>a: install from GitHub</Text>
        </Box>
      </Box>
    );
  }

  return (
    <Box flexDirection="column">
      {s.skills.map((skill, idx) => {
        const selected = idx === s.selectedIndex;
        return (
          <Box key={skill.name} flexDirection="column">
            <Box flexDirection="row">
              <Box width={2} flexShrink={0}>
                <Text color={selected ? accent : colors.text.disabled}>
                  {selected ? INDICATOR_SELECTED.trimEnd() : INDICATOR_UNSELECTED.trimEnd()}
                </Text>
              </Box>
              <Box width={10} flexShrink={0} marginLeft={1}>
                <Text color={LOCATION_COLORS[skill.location] ?? colors.text.secondary} bold>
                  {skill.location}
                </Text>
              </Box>
              <Text color={selected ? accent : colors.text.primary}>{skill.name}</Text>
            </Box>
            {selected && (
              <Box marginLeft={13}>
                <Text color={colors.text.muted} wrap="truncate">{skill.description}</Text>
              </Box>
            )}
          </Box>
        );
      })}
      {s.error && (
        <Box marginTop={1}>
          <Text color={colors.status.error}>{s.error}</Text>
        </Box>
      )}
      <Box marginTop={s.error ? 0 : 1}>
        <Text color={colors.text.disabled}>a: install  d: remove</Text>
      </Box>
    </Box>
  );
}

function InstallMode({ skills: s, accent }: SkillsSectionProps) {
  return (
    <Box flexDirection="column">
      <Text color={accent} bold>INSTALL FROM GITHUB</Text>
      <Box marginTop={1} flexDirection="row">
        <Box width={8} flexShrink={0}>
          <Text color={colors.text.secondary}>Source</Text>
        </Box>
        <TextInputField
          value={s.installSource}
          cursorPos={s.installCursor}
          placeholder="owner/repo/path/to/skill"
          showCursor={true}
        />
      </Box>
      <Box marginTop={1}>
        <Text color={colors.text.muted}>e.g. anthropics/skills/skills/pdf</Text>
      </Box>
      {s.installing && (
        <Box marginTop={1}>
          <Text color={colors.status.warning}>Installing...</Text>
        </Box>
      )}
      {s.error && (
        <Box marginTop={1}>
          <Text color={colors.status.error}>{s.error}</Text>
        </Box>
      )}
      <Box marginTop={1}>
        <Text color={colors.text.disabled}>Enter: install  Esc: cancel</Text>
      </Box>
    </Box>
  );
}

function ConfirmDeleteMode({ skills: s, accent }: SkillsSectionProps) {
  const skill = s.skills[s.selectedIndex];
  if (!skill) return null;

  return (
    <Box flexDirection="column">
      <Text color={colors.status.warning}>
        Remove skill <Text bold color={accent}>{skill.name}</Text>?
      </Text>
      <Box marginTop={1}>
        <Text color={colors.text.disabled}>y: confirm  n/Esc: cancel</Text>
      </Box>
    </Box>
  );
}

export function SkillsSection(props: SkillsSectionProps) {
  const { mode, loading } = props.skills;

  if (loading) {
    return <Text color={colors.text.muted}>Loading...</Text>;
  }

  if (mode === "list") return <ListMode {...props} />;
  if (mode === "install") return <InstallMode {...props} />;
  if (mode === "confirm-delete") return <ConfirmDeleteMode {...props} />;
  return null;
}
