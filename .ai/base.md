## How This File Works

This file is **auto-generated** by `.ai/scripts/sync.js` by concatenating two source files:
- `.ai/project.md` — project-specific context (MCP tools, skills, docs, code style)
- `.ai/base.md` — portable agent instructions, reusable across projects

**Never edit the generated files directly.** Edit the source files in `.ai/` and run `node .ai/scripts/sync.js` to regenerate.

The sync script writes the combined content to:

| Generated file | Harness |
|---|---|
| `CLAUDE.md` | Claude Code |
| `AGENTS.md` | OpenAI Codex / generic agents |
| `GEMINI.md` | Gemini CLI |
| `.github/copilot-instructions.md` | VS Code Copilot |

Skills and prompts are also synced:
- `.ai/skills/<name>.md` → `.claude/skills/<name>/SKILL.md` and `.github/skills/<name>/SKILL.md`
- `.ai/prompts/<name>.md` → `.claude/commands/<name>.md` and `.github/prompts/<name>.prompt.md`

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

## Source Accuracy & Drafting Protocol

Never fabricate statistics, data points, or claims not explicitly present in source documents. If a fact cannot be verified from provided sources, flag it as `[NEEDS SOURCE]` rather than including it. Cross-reference all data attributions to ensure they match the correct source document and author.

### When drafting documents or conducting research from source materials:

1. **Read first, write second.** Read all provided source documents fully before drafting. Do not begin writing until all sources are loaded.
2. **Maintain a source map.** Track every factual claim, metric, name, or date back to its source. Present the draft clean (no inline tags), with a "Source Map" appendix listing each claim and its origin (document name, section/heading).
3. **Verify before delivering.** For substantive documents (strategy docs, external-facing reports, review comments, posts, presentations), spawn a verification agent that re-reads each source and checks every claim in the source map. Mark any unverifiable claim as `[UNVERIFIED]`.
4. **Separate verified from unverified.** Present the clean draft with unverified claims removed, plus a separate list of removed claims so the user can decide whether to add them back with proper sourcing.
5. **No invention.** Never generate statistics, percentages, quotes, or specific details not found in the sources — even if they seem plausible or "directionally correct."
