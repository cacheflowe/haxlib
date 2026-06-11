---
name: validate-harness-sync
description: Use when the user asks to verify the AI agent harness is set up correctly, check whether sync targets exist, diagnose why a skill/prompt/MCP server isn't showing up, or confirm `.ai/` is wired into every harness (Claude Code, Codex, Copilot, Gemini CLI). Running this skill also serves as a self-test — if you can produce the report below, the skill loaded successfully.
---

## When to Use

Load this skill when the user asks any of:
- "Is my harness set up correctly?"
- "Validate my agent harness."
- "Why isn't my skill/prompt showing up in <tool>?"
- "Check that the sync ran."

It is **both** a diagnostic and a canary: a clean report proves the skill mechanism is working end-to-end (this skill was discovered, loaded, and acted on).

## How to Run the Check

Perform these steps in order and report results as a table. Do not summarize — list each check with PASS / FAIL / N/A so the user can spot the broken link.

### 1. Source of truth exists

Verify these are present in `.ai/`:

| Path | Required? |
|---|---|
| `.ai/scripts/sync.js` | Yes |
| `.ai/project.md` | Yes |
| `.ai/base.md` | Yes |
| `.ai/skills/` (directory) | Yes |
| `.ai/prompts/` (directory) | Yes |
| `.ai/mcp-servers.json` | Optional |

### 2. Composed context files

These are concatenated from `.ai/project.md` + `.ai/base.md` on every sync:

| Path | Harness |
|---|---|
| `CLAUDE.md` | Claude Code |
| `AGENTS.md` | Codex / generic |
| `GEMINI.md` | Gemini CLI |
| `.github/copilot-instructions.md` | VS Code Copilot |
| `.agents/context/AGENTS.md` | Codex `.agents/` layout |

For each: confirm the file exists. Then sanity-check that it actually contains the composed output by looking for a distinctive line from `.ai/project.md` (e.g. the `# Project Name — Agent Guide` heading). If a file exists but is empty or stale, the sync didn't run.

### 3. Skills are synced

For every `.ai/skills/<name>.md`, confirm:

- `.claude/skills/<name>/SKILL.md` exists
- `.agents/skills/<name>/SKILL.md` exists (real file, not a symlink — Codex requires this)
- `.github/skills/<name>/SKILL.md` exists

### 4. Prompts are synced

For every `.ai/prompts/<name>.md`, confirm:

- `.claude/skills/<name>/SKILL.md` exists (prompts share the skills dir in Claude Code)
- `.agents/skills/<name>/SKILL.md` exists (real file)
- `.github/prompts/<name>.prompt.md` exists
- `.gemini/commands/run/<name>.toml` exists, starts with `# ai-sync-generated`, and contains a `prompt = """..."""` block

### 5. MCP config (if `.ai/mcp-servers.json` exists)

- `.mcp.json` exists at repo root (symlink or copy — both fine)
- `.codex/config.toml` exists and starts with `# ai-sync-generated`
- `.gemini/settings.json` exists and contains an `mcpServers` key with the same server names as `.ai/mcp-servers.json`

If `.ai/mcp-servers.json` is absent, mark this section N/A (the sync logs `Source missing` warnings, which is normal).

### 6. Sync manifest

- `.ai/.sync-manifest.json` exists. Note its `updatedAt` timestamp — if it's far older than the most recent `.ai/` edit, the sync hasn't run since that edit.

### 7. Optional: git hooks

- `.githooks/post-merge` and `.githooks/post-checkout` exist.
- Run `git config core.hooksPath` and confirm it returns `.githooks`. If empty, the user needs to run `git config core.hooksPath .githooks` once per clone.

## Reporting

Output a single table with one row per check, columns: **Check**, **Status** (PASS / FAIL / N/A), **Detail** (file path or one-line reason). End with a "Next step" if anything failed — usually the fix is `node .ai/scripts/sync.js` followed by restarting the harness session.

## Common Failure Modes

| Symptom | Likely cause | Fix |
|---|---|---|
| Generated files missing | Sync never ran on this clone | `node .ai/scripts/sync.js` |
| Skill not in `.claude/skills/` but file is in `.ai/skills/` | Sync ran before the file was added | Re-run sync |
| Skill file exists but harness doesn't list it | Harness cached its skill index at session start | Restart the harness session |
| `.codex/config.toml` exists but the sync left it alone | First line is missing `# ai-sync-generated` marker — file treated as user-owned | Add the marker or delete the file and re-sync |
| `.gemini/settings.json` missing your server but other settings intact | Server name in `.ai/mcp-servers.json` differs from what you expect | Check the JSON source |
| `/run:<name>` not in Gemini's `/commands list` | TOML in wrong location or missing `prompt` field | Confirm `.gemini/commands/run/<name>.toml` exists, then `/commands reload` |

## Why This Doubles as a Canary

If you (the agent) read this far and produced the validation report, three things are proven:

1. The harness loaded the skill — so skill discovery works in the current tool.
2. The `description` frontmatter triggered correctly — so future skills with similar phrasing will also load.
3. You acted on the skill's instructions instead of paraphrasing them — confirming skill *content* (not just file presence) reaches the model.

If the user only wanted to test wiring and doesn't care about the harness state, you can simplify: "Skill loaded successfully. Run `node .ai/scripts/sync.js` if you want the full validation report."
