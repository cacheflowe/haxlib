# How It Works — Architecture of Agents Config Sync

This document explains the design of the toolkit: what problem it solves, the decisions behind its structure, and how the sync engine behaves. For the hands-on quickstart and authoring guide, see [.ai/README.md](.ai/README.md). For per-harness specifics, see [.ai/docs/harness-support.md](.ai/docs/harness-support.md).

---

## 1. Architectural Strategy

Modern AI engineering tools change too quickly to lock project rules into tool-specific hidden directories (`.claude/`, `.cursor/`, `.github/`, `.agents/`). This toolkit establishes a **vendor-agnostic workspace configuration** (`.ai/`, plus your project's `docs/`) as the single source of truth.

Tool-specific configurations are treated as **transient compilation targets**. A zero-dependency Node.js script ([.ai/scripts/sync.js](.ai/scripts/sync.js)) composes, links, or copies the source files to every location each harness expects. Node is the engine specifically because it behaves identically on macOS and Windows.

### Key consolidation decisions

- **One agent brief.** `.ai/AGENTS.md` (project-specific) + `.ai/_base.md` (portable toolkit instructions) are composed into root `AGENTS.md` (the de-facto cross-tool standard read by Codex, Antigravity CLI, Cursor, Amp, and others), `CLAUDE.md` (Claude Code), `.github/copilot-instructions.md` (VS Code Copilot), and `.agents/context/AGENTS.md` (Codex / Antigravity `.agents/` layout).
- **Inject, don't mutate.** The sync generates a skills, prompts, docs & MCP index at compose time and splices it *between* the two source files in the generated outputs only. Source files are never modified, so there are no marker-comment blocks to maintain and no risk of the script rewriting human-authored content.
- **One MCP config.** `.ai/mcp-servers.json` is the single source, fanned out per harness: `.mcp.json` (Claude Code + Copilot read it natively), `.pi/mcp.json` (`.pi` reads the same JSON shape from its own folder), `.codex/config.toml` (generated TOML), and `.agents/mcp_config.json` (generated JSON with Antigravity's `serverUrl` schema).
- **One skills folder.** Flat `.ai/skills/*.md` files are compiled into the `<name>/SKILL.md` folder wrappers required by Claude Code (`.claude/skills/`), Codex / Antigravity (`.agents/skills/`), and Copilot (`.github/skills/`).
- **One prompts folder.** Flat `.ai/prompts/*.md` files become slash commands everywhere: `.claude/skills/` (Claude Code treats prompts and skills the same), `.agents/skills/`, and `.github/prompts/<name>.prompt.md`. Authoring note: stick to portable frontmatter (`description`) and avoid tool-specific argument placeholders (Claude uses `$ARGUMENTS`/`$1`, Copilot uses `${input}`) — for shared prompts, prefer plain prose like "the user will specify the target."
- **No shared tool-config TOML.** Metadata lives in the markdown files themselves (frontmatter); generated config files exist only where a harness demands its own format.

---

## 2. Composition & the Injected Index

Every composed context file is built from three parts, in order:

1. `.ai/AGENTS.md` — project-specific context (overview, key directories, code style)
2. A **generated index** — rebuilt fresh on every sync:
   - `### Skills` — every `.ai/skills/*.md`, with its frontmatter `description`
   - `### Prompts (slash commands)` — every `.ai/prompts/*.md`, same treatment
   - `### Project Docs` — every `docs/**/*.md` (recursive), description from frontmatter or falling back to the first `# ` heading
   - `### MCP Servers` — informational list from `.ai/mcp-servers.json` (optional `description` key per server, falling back to the launch command or URL)
3. `.ai/_base.md` — portable agenct sync toolkit instructions, identical across projects

The result is written to all four composed targets and stamped with a trailing `<!-- ai-sync-generated -->` marker. On later runs, a file at a composed path that *lacks* the marker is treated as a local override and preserved untouched.

This split is the core authoring rule: **`.ai/AGENTS.md` holds only what is true for this repo; `.ai/_base.md` holds only what is true for every repo that adopts the toolkit.** The index in between is machine-maintained, so neither source ever needs a manual link list.

---

## 3. Sync Engine Behavior

- **Symlink first, copy fallback.** On macOS (and Windows with Developer Mode), assets are symlinked — zero overhead, live updates. Without symlink permission, the engine copies the source **verbatim** (no injected header — a prepended comment would corrupt skill/prompt frontmatter that must start at byte 0) and records hashes in `.ai/.sync-manifest.json` for stale-cleanup bookkeeping.
- **Skills & prompts: source of truth always wins.** Generated skill/prompt copies (`.claude/skills/`, `.github/skills/`, `.agents/skills/`, `.github/prompts/`, `.claude/commands/`) are pure derivatives of `.ai/skills/` and `.ai/prompts/`. They are never hand-edited (edit the source instead) and are **always regenerated** — a write is skipped only when the copy is already byte-identical. The sync does *not* try to preserve a drifted copy as a "local override": the old manifest-hash guard silently froze copies whenever the gitignored manifest was lost or drifted, serving stale content to Codex/Antigravity.
- **Ownership markers for composed/config files.** Composed markdown ends with `<!-- ai-sync-generated -->`; the Codex TOML must start with `# ai-sync-generated`; the Antigravity JSON carries a top-level `"_ai_sync_generated": true`. A composed/config file at a generated path missing its marker is treated as human-owned and never overwritten.
- **User-authored extras are still safe.** A skill/prompt whose *name* has no source under `.ai/` is never visited by the sync, so a hand-created file like `.claude/skills/personal-rule/SKILL.md` is left untouched.
- **Real files where selectors require them.** `.agents/skills/` receives file copies rather than symlinks — Codex and Antigravity skill selectors don't follow symlinks reliably.
- **Stale cleanup.** Skills/prompts deleted from `.ai/` have their generated counterparts removed from every target. When `mcpServers` is empty (or the source file is missing), all four MCP destinations are skipped and previously-generated stubs the sync still owns are cleaned up.
- **Idempotent.** Safe to run repeatedly from any trigger; unchanged outputs are left alone.
- **Watch mode.** `node .ai/scripts/sync.js --watch` uses Node's built-in `fs.watch` with `{ recursive: true }` on `.ai/`, debounced at 300ms. Note it only watches `.ai/` — edits under `docs/` are picked up on the next sync run.

---

## 4. Git Configuration

### `.gitignore`

Only *generated* artifacts are ignored — explicitly, never wholesale. Do **not** ignore all of `.claude/` (shared `settings.json` and hooks belong in version control) or all of `.github/` (workflows, tracked config). The current block:

```text
/AGENTS.md
/CLAUDE.md
/.mcp.json
/.pi/mcp.json
/.pi/mcp.json
/.github/copilot-instructions.md
/.github/prompts/
/.github/skills/
/.claude/skills/
/.claude/commands/
/.agents/skills/
/.agents/context/
/.agents/mcp_config.json
/.codex/
/.ai/.sync-manifest.json
.claude/settings.local.json
```

> **Trade-off:** because the root `AGENTS.md`/`CLAUDE.md` are generated and gitignored, a fresh clone (or the GitHub web UI) won't show them until the sync runs. If GitHub rendering matters for a repo, commit the generated root files and remove them from `.gitignore` — the marker/guardrail system tolerates this.

### `.gitattributes`

Git hooks must keep LF line endings on every platform (Git for Windows runs them with its bundled `sh.exe`):

```text
.githooks/* text eol=lf
```

---

## 5. Sync Triggers

The sync is idempotent, so all triggers coexist and behave identically on macOS and Windows:

| Trigger | Mechanism |
|---|---|
| Manual | `node .ai/scripts/sync.js` or `npm run ai-sync` |
| npm install | `postinstall` script in `package.json` |
| Git pull / merge | `.githooks/post-merge` (requires one-time `git config core.hooksPath .githooks`) |
| Git checkout | `.githooks/post-checkout` |
| VS Code folder open | `.vscode/tasks.json` task with `"runOn": "folderOpen"` |
| Authoring sessions | `node .ai/scripts/sync.js --watch` |

---

## 6. Coexistence Rules

1. **Global/personal machine overrides** (API credentials, default models, personal rules) live in global user config (`~/.claude/CLAUDE.md`, `~/.claude/settings.json`, VS Code user settings) — never in the repository.
2. **Local-only experiments**: hand-created files at generated paths are preserved by the guardrail mechanism (see §3).
3. **Tracked Claude settings**: shared `.claude/settings.json` (permissions, hooks) is version-controlled; only `.claude/settings.local.json` is ignored.
4. **Root-relative links**: all cross-references in `.ai/` sources must be root-relative (e.g. `[.ai/docs/harness-support.md](.ai/docs/harness-support.md)`). Symlinks resolve relative links from the *link's* location, not the source's — root-relative paths work from the repo root and from `.github/`/`.claude/` alike. They may appear broken when browsing inside `.ai/` in an editor; that's the accepted trade-off.
5. **Context hygiene**: pair the harness with a tracked `.editorconfig` and per-tool ignore files (e.g. `.cursorignore`) where needed, so agents don't burn tokens on formatting rules or heavyweight noise.

---

## 7. Adoption Strategies

### A — Template repository (new projects)

Commit this structure, mark the repo as a **Template repository** on GitHub, and teammates click **Use this template**, then run `git config core.hooksPath .githooks` and `node .ai/scripts/sync.js` (or `npm install`).

### B — Retrofit (existing projects)

1. Copy `.ai/`, `.githooks/`, `.gitattributes`, and the `.vscode/tasks.json` task into the repo.
2. Move existing instruction files (`CLAUDE.md`, `AGENTS.md`, `copilot-instructions.md`) into `.ai/AGENTS.md` (project-specific) and `.ai/_base.md` (portable), converting links to root-relative paths; move existing skills into flat `.ai/skills/*.md` files.
3. Delete the originals, merge the §4 `.gitignore` block, and run the sync — the originals are regenerated.
4. Optionally maintain `.ai/` as a **git submodule or subtree** shared across an ecosystem of projects, so prompt/skill improvements propagate with a single update. Keep project-specific content (`.ai/AGENTS.md`, `docs/`) outside the shared module.
