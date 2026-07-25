---
name: update-docs
description: Audit recent code changes and update every documentation location that reflects them — .ai/skills/, .ai/AGENTS.md, .ai/docs/, project-level docs/, and the root README.md — then re-run the sync. Use after changing code, patterns, sync targets, or harness behavior.
---

Audit the project's documentation against recent code changes and bring every affected location up to date.

## 1. Identify what changed

- If the user specified the changes to document, start from those.
- Otherwise inspect, in order: unstaged/staged changes (`git status`, `git diff`), then recent commits (`git log --oneline -10` and diffs) until you have a clear picture of what behavior, patterns, or structure changed.

## 2. Check each documentation location

For every change, check whether these locations reference the old behavior or should describe the new one:

1. **`.ai/skills/`** — domain knowledge files: new features or APIs, renamed concepts, deprecated patterns, changed workflows
2. **`.ai/AGENTS.md`** — project-specific context: key directories, code style, MCP tools
3. **`.ai/_base.md`** — portable harness instructions: sync targets, generated-file tables, conventions
4. **`.ai/docs/`** — harness docs: `README.md` (quickstart/structure), `how-it-works.md` (architecture/design rationale), `harness-support.md` (per-harness reference), `test-instructions.md` (verification)
5. **`docs/`** (if present) — your project's own architecture, guides, references
6. **`README.md`** (root) — thin stub pointing into `.ai/docs/`; update only if top-level orientation changes

**Cross-Reference Check**: If a skill is modified, ensure its corresponding prompt and command definitions are also checked for consistency. If a prompt is modified, ensure its skill is also checked.

Search for stale references (old names, removed flags, outdated paths) rather than only adding new text.

## 3. Make the edits

- Edit **`.ai/` sources only** — never the generated files (`CLAUDE.md`, `AGENTS.md`, `.github/copilot-instructions.md`, `.agents/context/AGENTS.md`, etc.).
- Use root-relative paths for all cross-references (e.g. `[.ai/docs/harness-support.md](.ai/docs/harness-support.md)`).
- New skills, prompts, and `docs/` files are indexed automatically — the sync script generates the index and injects it into the composed outputs, so don't add manual link lists to `.ai/AGENTS.md`.
- Don't fabricate details — document only what the code changes actually do.

## 4. Sync and report

- Run `node .ai/scripts/sync.js` to regenerate all harness targets.
- **Verify Sync**: Inspect the output of the sync script. Ensure no errors were reported and that all expected files were linked or copied.
- Report: which files were updated and why, and which locations were checked but needed no changes.
