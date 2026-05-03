import { colors, truncateText, TextInputField } from "../../../ui/index.js";
import { Row, StatusMessage } from "../SettingsRows.js";
import type { UseSkillsResult } from "../../../../hooks/useSkills.js";

interface SkillsSectionProps {
  skills: UseSkillsResult;
  accent: string;
  width: number;
  height: number;
}

function ListMode({ skills: s, accent, width, height }: SkillsSectionProps) {
  if (s.skills.length === 0) {
    return (
      <box flexDirection="column">
        <text><span fg={colors.text.muted}>No skills installed</span></text>
      </box>
    );
  }

  const linesPerItem = 2;
  const reservedLines = 2;
  const visibleCount = Math.max(1, Math.floor((height - reservedLines) / linesPerItem));
  const maxStart = Math.max(0, s.skills.length - visibleCount);
  const scrollStart = Math.min(maxStart, Math.max(0, s.selectedIndex - visibleCount + 1));
  const visibleSkills = s.skills.slice(scrollStart, scrollStart + visibleCount);

  const nameMaxWidth = Math.max(10, width - 2);
  const descWidth = Math.max(10, width - 4);

  return (
    <box flexDirection="column" width={width}>
      {visibleSkills.map((skill, vi) => {
        const idx = scrollStart + vi;
        const selected = idx === s.selectedIndex;
        const nameAndLoc = skill.name + " " + skill.location;
        const clipped = nameAndLoc.length > nameMaxWidth
          ? nameAndLoc.slice(0, nameMaxWidth - 1) + "\u2026"
          : nameAndLoc;
        return (
          <box key={skill.name} flexDirection="column">
            <Row selected={selected} accent={accent} arrow>
              <text><span fg={selected ? accent : colors.text.primary}>{clipped}</span></text>
            </Row>
            <box marginLeft={2}>
              <text><span fg={colors.text.muted}>{truncateText(skill.description, descWidth)}</span></text>
            </box>
          </box>
        );
      })}
      {s.error && <StatusMessage color={colors.status.error}>{s.error}</StatusMessage>}
    </box>
  );
}

function InstallMode({ skills: s, accent }: SkillsSectionProps) {
  return (
    <box flexDirection="column">
      <text><span fg={accent}><strong>INSTALL FROM GITHUB</strong></span></text>
      <box marginTop={1} flexDirection="row">
        <box width={8} flexShrink={0}>
          <text><span fg={colors.text.secondary}>Source</span></text>
        </box>
        <TextInputField
          value={s.installSource}
          cursorPos={s.installCursor}
          placeholder="owner/repo/path/to/skill"
          showCursor={true}
        />
      </box>
      <box marginTop={1}>
        <text><span fg={colors.text.muted}>e.g. anthropics/skills/skills/pdf</span></text>
      </box>
      {s.installing && <StatusMessage color={colors.status.warning}>Installing...</StatusMessage>}
      {s.error && <StatusMessage color={colors.status.error}>{s.error}</StatusMessage>}
    </box>
  );
}

function ConfirmDeleteMode({ skills: s, accent }: SkillsSectionProps) {
  const skill = s.skills[s.selectedIndex];
  if (!skill) return null;

  return (
    <box flexDirection="column">
      <text>
        <span fg={colors.status.warning}>Remove skill </span>
        <span fg={accent}><strong>{skill.name}</strong></span>
        <span fg={colors.status.warning}>?</span>
      </text>
    </box>
  );
}

export function SkillsSection(props: SkillsSectionProps) {
  const { mode, loading } = props.skills;

  if (loading) {
    return <text><span fg={colors.text.muted}>Loading...</span></text>;
  }

  if (mode === "list") return <ListMode {...props} />;
  if (mode === "install") return <InstallMode {...props} />;
  if (mode === "confirm-delete") return <ConfirmDeleteMode {...props} />;
  return null;
}
