---
name: obsidian
description: Work with Obsidian vaults through the official `obsidian` CLI or an external Obsidian MCP server.
---

# Obsidian

Use this skill when the user asks to search, read, create, rename, move, or delete Obsidian notes.

ntrp has no native Obsidian integration. Prefer an external Obsidian MCP server when it is connected and exposes the needed operation. Otherwise use `bash` with the official `obsidian` CLI, plus `read_file` for direct Markdown reads.

Obsidian CLI requires the Obsidian app CLI to be enabled in Obsidian settings. Check availability with:

```bash
obsidian help
```

## Vault model

An Obsidian vault is a normal folder on disk:

- Notes are `*.md` files.
- `.obsidian/` contains workspace and plugin settings; do not edit it unless explicitly asked.
- `*.canvas` files are JSON.
- Attachments live wherever the user's Obsidian settings put them.

## Target the vault

If the shell is already inside a vault folder, Obsidian CLI targets that vault. Otherwise it targets the active vault. To inspect known vaults:

```bash
obsidian vaults verbose
```

To get the active vault path:

```bash
obsidian vault info=path
```

When the user names a specific vault, pass it as the first parameter:

```bash
obsidian vault="Work Notes" search query="project"
```

## Common commands

Search matching files:

```bash
obsidian search query="meeting notes"
```

Search with matching line context:

```bash
obsidian search:context query="meeting notes"
```

Read a note:

```bash
obsidian read path="Folder/Note.md"
```

You can also use `file=<name>` when a wikilink-style file name uniquely resolves:

```bash
obsidian read file=Recipe
```

Create a note:

```bash
obsidian create path="Folder/New note.md" content="# Title\n\nBody" open
```

Move or rename a note:

```bash
obsidian move path="old/path.md" to="new/path.md"
obsidian rename path="old/path.md" name="New name"
```

Use `obsidian move` or `obsidian rename` instead of `mv` when renaming notes. Obsidian can update internal links if the vault setting for automatically updating internal links is enabled.

Delete a note:

```bash
obsidian delete path="Folder/Note.md"
```

Deletion uses the trash by default. Use `permanent` only when the user explicitly asks for permanent deletion.

## Direct Markdown edits

For normal content edits, it is often simpler to edit the `.md` file directly once the vault path is known. Obsidian will pick up file changes.

Before editing:

1. Resolve the vault path.
2. Locate the note with `obsidian search`, `obsidian search:context`, or filesystem search.
3. Read the file with `read_file`.
4. Make the smallest direct Markdown edit needed.

For structural operations, prefer `obsidian`:

- Rename or move notes with `obsidian move` or `obsidian rename`.
- Create notes with `obsidian create` when the user wants Obsidian to open the result.
- Delete notes with `obsidian delete` only after confirming the exact target.
