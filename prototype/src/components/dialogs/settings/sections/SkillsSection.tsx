import { colors, TextInputField } from "../../../ui/index.js";
import type { UseSkillsResult } from "../../../../hooks/useSkills.js";
import { INDICATOR_SELECTED, INDICATOR_UNSELECTED } from "../../../../lib/constants.js";

interface SkillsSectionProps {
  skills: UseSkillsResult;
  accent: string;
}

const LOCATION_COLORS: Record<string, string> = {
  project: colors.text.primary,
  global: colors.text.secondary,
};

function ListMode({ skills: s, accent }: SkillsSectionProps) {
  if (s.skills.length === 0) {
    return (
      <box flexDirection="column">
        <text><span fg={colors.text.muted}>No skills installed</span></text>
        <box marginTop={1}>
          <text><span fg={colors.text.disabled}>a: install from GitHub</span></text>
        </box>
      </box>
    );
  }

  return (
    <box flexDirection="column">
      {s.skills.map((skill, idx) => {
        const selected = idx === s.selectedIndex;
        return (
          <box key={skill.name} flexDirection="column">
            <box flexDirection="row">
              <box width={2} flexShrink={0}>
                <text>
                  <span fg={selected ? accent : colors.text.disabled}>
                    {selected ? INDICATOR_SELECTED.trimEnd() : INDICATOR_UNSELECTED.trimEnd()}
                  </span>
                </text>
              </box>
              <box width={10} flexShrink={0} marginLeft={1}>
                <text>
                  <span fg={LOCATION_COLORS[skill.location] ?? colors.text.secondary}><strong>{skill.location}</strong></span>
                </text>
              </box>
              <text><span fg={selected ? accent : colors.text.primary}>{skill.name}</span></text>
            </box>
            {selected && (
              <box marginLeft={13}>
                <text><span fg={colors.text.muted}>{skill.description}</span></text>
              </box>
            )}
          </box>
        );
      })}
      {s.error && (
        <box marginTop={1}>
          <text><span fg={colors.status.error}>{s.error}</span></text>
        </box>
      )}
      <box marginTop={s.error ? 0 : 1}>
        <text><span fg={colors.text.disabled}>a: install  d: remove</span></text>
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
        <text><span fg={colors.text.disabled}>Enter: install  Esc: cancel</span></text>
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
        <text><span fg={colors.text.disabled}>y: confirm  n/Esc: cancel</span></text>
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
