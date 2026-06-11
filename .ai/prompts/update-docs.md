---
name: update-docs
description: Audit recent code changes and update every documentation location that reflects them — .ai/skills/, .ai/project.md, .ai/docs/, project-level docs/, and the root README.md — then re-run the sync. Use after changing code, patterns, sync targets, or harness behavior.
---

Audit the project's documentation against recent code changes and bring every affected location up to date.

## 1. Identify what changed

- If the user specified the changes to document, start from those.
- Otherwise inspect, in order: unstaged/staged changes (`git status`, `git diff`), then recent commits (`git log --oneline -10` and diffs) until you have a clear picture of what behavior, patterns, or structure changed.

## 2. Check each documentation location

For every change, check whether these locations reference the old behavior or should describe the new one:

1. **`.ai/skills/`** — domain knowledge files: new features or APIs, renamed concepts, deprecated patterns, changed workflows
2. **`.ai/project.md`** — Skills & Docs index, key directories, code style, MCP tools
3. **`.ai/base.md`** — portable harness instructions: sync targets, generated-file tables, conventions
4. **`.ai/docs/`** — harness docs: `README.md` (quickstart/structure), `harness-support.md` (per-harness reference), `test-instructions.md` (verification)
5. **`docs/`** (if present) — your project's own architecture, guides, references
6. **`README.md`** (root) — thin stub pointing into `.ai/docs/`; update only if top-level orientation changes

Search for stale references (old names, removed flags, outdated paths) rather than only adding new text.

## 3. Make the edits

- Edit **`.ai/` sources only** — never the generated files (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `.github/copilot-instructions.md`, etc.).
- Use root-relative paths for all cross-references (e.g. `[.ai/docs/harness-support.md](.ai/docs/harness-support.md)`).
- If a new skill or doc was created, add it to the Skills & Docs section of `.ai/project.md`.
- Don't fabricate details — document only what the code changes actually do.

## 4. Sync and report

- Run `node .ai/scripts/sync.js` to regenerate all harness targets.
- Report: which files were updated and why, and which locations were checked but needed no changes.
