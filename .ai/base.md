## How This File Works

This file is **auto-generated** by `.ai/scripts/sync.js` by concatenating two source files:
- `.ai/project.md` — project-specific context (MCP tools, skills, docs, code style)
- `.ai/base.md` — portable agent instructions, reusable across projects

**Never edit the generated files directly.** Edit the source files in `.ai/` and run `node .ai/scripts/sync.js` to regenerate. Memory should be kept in `.ai/project.md` rather than CLAUDE.md or AGENTS.md to ensure it is included in all agent contexts. Only project-specific details should go in `.ai/project.md` — everything else belongs in `.ai/base.md` to be shared for agent consistency.

The sync script writes the combined content to:

| Generated file | Harness |
|---|---|
| `CLAUDE.md` | Claude Code |
| `AGENTS.md` | OpenAI Codex / generic agents |
| `GEMINI.md` | Gemini CLI |
| `.github/copilot-instructions.md` | VS Code Copilot |
| `.agents/context/AGENTS.md` | Codex `.agents/` layout |

Skills and prompts are also synced:

| Source | Claude Code | Codex | Copilot | Gemini CLI |
|---|---|---|---|---|
| `.ai/skills/<name>.md` | `.claude/skills/<name>/SKILL.md` | `.agents/skills/<name>/SKILL.md` | `.github/skills/<name>/SKILL.md` | — (use context only) |
| `.ai/prompts/<name>.md` | `.claude/skills/<name>/SKILL.md` | `.agents/skills/<name>/SKILL.md` | `.github/prompts/<name>.prompt.md` | `.gemini/commands/run/<name>.toml` (invoked as `/run:<name>`) |

MCP config is also synced:
- `.ai/mcp-servers.json` → `.mcp.json` (Claude Code), `.codex/config.toml` (Codex), and `.gemini/settings.json` (Gemini CLI, merged under the `mcpServers` key)

The Codex TOML is generated from the JSON source. If `.codex/config.toml` doesn't start with the `# ai-sync-generated` marker, it's treated as a user-owned file and left untouched.

The Gemini target is a merge, not an overwrite: other keys in `.gemini/settings.json` and user-added servers with different names are preserved; servers named in `.ai/mcp-servers.json` are authoritative.

Both use the same YAML frontmatter format. The `description` field is required — it's what Claude Code reads to decide when to load the skill:
```yaml
---
name: My Skill
description: One-line description Claude uses to decide when to load this skill
---
```

Note: `.claude/commands/` is deprecated. The sync script automatically migrates any generated entries there to `.claude/skills/`.

Run `node .ai/scripts/sync.js` to sync manually, or `node .ai/scripts/sync.js --watch` to sync on file changes.

### Authoring Convention: Root-Relative Links

All cross-references inside `.ai/` source files (links to skills, docs, or other markdown) **must use root-relative paths**, e.g.:

```markdown
See [docs/systemArchitecture.md](docs/systemArchitecture.md) and
[.ai/skills/code-reviewer.md](.ai/skills/code-reviewer.md).
```

Symlinks resolve relative paths from the *link's location*, not the source file's. Since generated targets land at the repo root (`CLAUDE.md`, `AGENTS.md`) and inside `.github/`/`.claude/`, root-relative links work everywhere the files are consumed. Links may appear broken when navigating the `.ai/` source in an editor — that is expected.

### Global vs. Project Settings

Machine-specific preferences (API credentials, default models, personal rules) belong in global user config (`~/.claude/CLAUDE.md`, `~/.claude/settings.json`) — never committed to the repository. Shared project settings (permissions, hooks) go in `.claude/settings.json`, which is tracked. Only `.claude/settings.local.json` is gitignored.

---

## Documentation Maintenance

The `.ai/` sources (including `.ai/docs/`) and any project-level `docs/` folder are the project's living knowledge base. **Whenever you change code, patterns, or harness behavior, update every documentation location that reflects the change — in the same piece of work, not as a follow-up.**

Check each of these locations and update any that are affected:

1. **`.ai/skills/`** — domain knowledge: new features or APIs, renamed concepts, deprecated patterns, changed workflows
2. **`.ai/project.md`** — project context: the Skills & Docs index, key directories, code style, MCP tools
3. **`.ai/docs/`** — harness documentation: `README.md` (quickstart/structure), `harness-support.md` (per-harness reference), `test-instructions.md` (verification steps)
4. **`docs/`** (if present) — your project's own living docs: architecture, guides, references
5. **`README.md`** (root) — thin stub that points into `.ai/docs/`; update if the top-level orientation changes

This includes:
- New features or APIs → add or update the relevant skill or doc
- Renamed concepts or operators → fix references across skills and docs
- Deprecated patterns → mark them in the relevant file
- Bug fixes that change documented behavior → update the doc
- New or changed sync targets, harnesses, or config formats → update `.ai/README.md` tables and `.ai/docs/harness-support.md`

Remember: edit `.ai/` sources, never the generated files, and run `node .ai/scripts/sync.js` after. The `/update-docs` command ([.ai/prompts/update-docs.md](.ai/prompts/update-docs.md)) runs this audit on demand.

---

## Source Accuracy & Drafting Protocol

Never fabricate statistics, data points, or claims not explicitly present in source documents. If a fact cannot be verified from provided sources, flag it as `[NEEDS SOURCE]` rather than including it. Cross-reference all data attributions to ensure they match the correct source document and author.

### When drafting documents or conducting research from source materials:

1. **Read first, write second.** Read all provided source documents fully before drafting. Do not begin writing until all sources are loaded.
2. **Maintain a source map.** Track every factual claim, metric, name, or date back to its source. Present the draft clean (no inline tags), with a "Source Map" appendix listing each claim and its origin (document name, section/heading).
3. **Verify before delivering.** For substantive documents (strategy docs, external-facing reports, review comments, posts, presentations), spawn a verification agent that re-reads each source and checks every claim in the source map. Mark any unverifiable claim as `[UNVERIFIED]`.
4. **Separate verified from unverified.** Present the clean draft with unverified claims removed, plus a separate list of removed claims so the user can decide whether to add them back with proper sourcing.
5. **No invention.** Never generate statistics, percentages, quotes, or specific details not found in the sources — even if they seem plausible or "directionally correct."
