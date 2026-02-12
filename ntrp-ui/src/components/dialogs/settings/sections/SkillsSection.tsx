import { colors, truncateText, TextInputField, Hints } from "../../../ui/index.js";
import type { UseSkillsResult } from "../../../../hooks/useSkills.js";

interface SkillsSectionProps {
  skills: UseSkillsResult;
  accent: string;
  width: number;
}

function ListMode({ skills: s, accent, width }: SkillsSectionProps) {
  if (s.skills.length === 0) {
    return (
      <box flexDirection="column">
        <text><span fg={colors.text.muted}>No skills installed</span></text>
        <box marginTop={1}>
          <Hints items={[["a", "install from GitHub"]]} />
        </box>
      </box>
    );
  }

  const descWidth = Math.max(10, width - 4);

  return (
    <box flexDirection="column" width={width}>
      {s.skills.map((skill, idx) => {
        const selected = idx === s.selectedIndex;
        return (
          <box key={skill.name} flexDirection="column">
            <text>
              <span fg={selected ? accent : colors.text.disabled}>{selected ? "▸ " : "  "}</span>
              <span fg={selected ? accent : colors.text.primary}>{skill.name}</span>
              <span fg={colors.text.disabled}> {skill.location}</span>
            </text>
            <text>
              <span fg={colors.text.muted}>{"  "}{truncateText(skill.description, descWidth)}</span>
            </text>
          </box>
        );
      })}
      {s.error && (
        <box marginTop={1}>
          <text><span fg={colors.status.error}>{s.error}</span></text>
        </box>
      )}
      <box marginTop={1}>
        <Hints items={[["a", "install"], ["d", "remove"]]} />
      </box>
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
      {s.installing && (
        <box marginTop={1}>
          <text><span fg={colors.status.warning}>Installing...</span></text>
        </box>
      )}
      {s.error && (
        <box marginTop={1}>
          <text><span fg={colors.status.error}>{s.error}</span></text>
        </box>
      )}
      <box marginTop={1}>
        <Hints items={[["enter", "install"], ["esc", "cancel"]]} />
      </box>
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
      <box marginTop={1}>
        <Hints items={[["y", "confirm"], ["n/esc", "cancel"]]} />
      </box>
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
