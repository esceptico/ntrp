---
name: add-skill
description: Use this skill when the user wants to create a new skill or remove an existing skill. This includes writing a SKILL.md from scratch and adding scripts/assets.
---

# Add / Remove a Skill

Skills live in two places:
- **Builtin**: shipped with ntrp, don't touch
- **Global**: `~/.ntrp/skills/` — user skills, create here

A skill is a directory containing at minimum a `SKILL.md` file.

## Directory structure

```
~/.ntrp/skills/my-skill/
├── SKILL.md          # required
├── scripts/          # optional: executable scripts
├── references/       # optional: extra docs loaded on demand
└── assets/           # optional: templates, data files
```

## SKILL.md format

```markdown
---
name: my-skill
description: What it does and WHEN to use it. Be specific — this is what I read to decide whether to activate the skill.
---

# Skill Title

Step-by-step instructions...
```

### Frontmatter rules
- `name`: lowercase, hyphens only, must match directory name, max 64 chars
- `description`: max 1024 chars — include keywords that match user intent
- Both fields are required

## Creating a skill

1. `mkdir -p ~/.ntrp/skills/<name>/scripts`
2. Write `SKILL.md` with frontmatter + instructions
3. Add any scripts to `scripts/` — reference them by relative path in SKILL.md
4. No restart needed — skills are loaded on demand

## Removing a skill

Delete the directory. Only global skills can be removed (not builtins).

## Listing installed skills

```bash
ls ~/.ntrp/skills/
ls /Users/escept1co/src/ntrp/skills/
```

## After creating

- Skills are discovered on demand via `use_skill` — no restart needed
- Test by calling `use_skill(skill="<name>")`

## Tips

- Keep `SKILL.md` under 500 lines — move heavy reference material to `references/`
- Scripts should be self-contained with clear error messages
- The skill's absolute path is injected as `<skill_path>` at load time — use it to reference sibling files
