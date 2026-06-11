# `.ai/` — Cross-Harness Agent Configuration

This folder is the **source of truth** for AI agent context across Claude Code, OpenAI Codex, VS Code Copilot, Gemini CLI, Cursor, and others. A zero-dependency Node.js sync script in [.ai/scripts/sync.js](.ai/scripts/sync.js) fans these source files out to every harness's expected paths so you author once and every tool sees the same instructions.

If you've just dropped `.ai/` into a new project, start with the [Quickstart](#quickstart) below. If you're trying to add a skill, prompt, or MCP server, jump to [Adding things](#adding-things).

---

## What you edit vs. what's generated

The harness only works if you stay on the right side of this line.

### Edit these (sources)

| Path | Purpose |
|---|---|
| `.ai/project.md` | Project-specific agent instructions (what *this* repo is, key dirs, skills index) |
| `.ai/base.md` | Portable instructions reusable across repos |
| `.ai/mcp-servers.json` | MCP server definitions (optional — create if needed) |
| `.ai/skills/<name>.md` | Domain knowledge agents load when relevant |
| `.ai/prompts/<name>.md` | Slash commands you invoke explicitly |

### Don't edit these (harness internals)

These ship with the harness and are maintained by the agents-harness-starter project. Touch them only if you're upstreaming improvements to the harness itself — adopters should leave them alone so they can pull future updates cleanly.

| Path | Why |
|---|---|
| `.ai/scripts/sync.js` | Sync engine — only modify if extending sync behavior |
| `.ai/.sync-manifest.json` | Generated state; regenerated on every sync |
| `.ai/docs/*.md` | Harness reference docs (per-harness support, test instructions, setup notes) |
| `.ai/README.md` | This file — documents the harness itself |

### Never edit these (generated harness targets)

These are produced from `.ai/` sources on every sync. They are **gitignored** and any direct edits will be overwritten.

| Path | Harness |
|---|---|
| `CLAUDE.md`, `AGENTS.md`, `GEMINI.md` | Claude Code, Codex, Gemini CLI |
| `.github/copilot-instructions.md` | VS Code Copilot |
| `.agents/context/AGENTS.md` | Codex `.agents/` layout |
| `.claude/skills/<name>/SKILL.md` | Claude Code skills + prompts |
| `.claude/commands/<name>.md` | Claude Code commands (deprecated location, still written for CLI compat) |
| `.agents/skills/<name>/SKILL.md` | Codex skills + prompts (real file copies — Codex selectors don't follow symlinks) |
| `.github/skills/<name>/SKILL.md` | Copilot skills |
| `.github/prompts/<name>.prompt.md` | Copilot prompts |
| `.gemini/commands/run/<name>.toml` | Gemini CLI commands (invoked as `/run:<name>`) |
| `.gemini/settings.json` | Gemini CLI MCP servers (merged — your other settings are preserved) |
| `.mcp.json` | Claude Code + Copilot MCP config (symlink to `.ai/mcp-servers.json`) |
| `.codex/config.toml` | Codex MCP config (generated TOML) |

Whenever you change a source, run `node .ai/scripts/sync.js` (or let one of the [automatic triggers](#when-the-sync-runs-automatic-triggers) handle it).

---

## Quickstart

### 1. Copy the harness files into your repo

```bash
# From this template, copy these into your existing project:
cp -r .ai/ <your-project>/.ai/
cp -r .githooks/ <your-project>/.githooks/
cp .gitattributes <your-project>/  # merge if you already have one
```

Merge the `.gitignore` entries and `package.json` scripts into your existing files (or copy them if you don't have them yet). The `.gitignore` block is under the `# Cross-AI Tooling` comment — copy everything from that comment through `.ai/mcp-servers.json`.

Merge the following task into your `.vscode/tasks.json` (create it if needed, or add the task entry to the existing `tasks` array):

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "ai-sync",
      "type": "shell",
      "command": "node .ai/scripts/sync.js",
      "runOptions": { "runOn": "folderOpen" },
      "presentation": { "reveal": "silent" }
    }
  ]
}
```

### 2. Move existing agent instructions into `.ai/`

If you already have `CLAUDE.md`, `AGENTS.md`, or `.github/copilot-instructions.md`, move their content into `.ai/project.md` (project-specific) or `.ai/base.md` (portable/reusable). Delete the originals — the sync will regenerate them.

### 3. Run the sync

```bash
node .ai/scripts/sync.js
# or, if you're running npm install anyway:
npm install  # postinstall runs the sync automatically
```

> **Fresh-clone note**: the generated files (`CLAUDE.md`, `AGENTS.md`, etc.) are gitignored and must be regenerated after every clone. The `postinstall` script handles this automatically — teammates just need to run `npm install` before opening the project in an AI tool.

### 4. Enable git hooks

```bash
git config core.hooksPath .githooks
```

This auto-syncs on `git pull` and `git checkout`.

### 5. Verify it works

Either ask any harness "is my agent harness set up correctly?" (the [validate-harness-sync](.ai/skills/validate-harness-sync.md) skill will load and produce a PASS/FAIL report), or follow the manual checklist in [.ai/docs/test-instructions.md](.ai/docs/test-instructions.md).

### 6. (Recommended) Bootstrap a `docs/` tree for your project

Run the [`harness-setup`](.ai/prompts/harness-setup.md) prompt in any agent (`/harness-setup` in Claude Code / Copilot / Codex, `/run:harness-setup` in Gemini CLI). It restructures your repo into an opinionated, agent-friendly `docs/` tree — `ARCHITECTURE.md`, `COMMANDS.md`, `DESIGN.md`, `FRONTEND.md`, `BACKEND.md`, `SECURITY.md`, plus `design-docs/`, `product-specs/`, `exec-plans/`, and `references/` subtrees — with a short root agent map that links into them.

This is the second big opinion this toolkit ships (alongside the cross-harness sync): a "system of record" docs layout that gives AI tools deep, navigable context via progressive disclosure. If you're dropping the harness into an existing project, running this once produces a *lot* of high-quality context for agents to work from. The prompt's body (see [.ai/prompts/harness-setup.md](.ai/prompts/harness-setup.md)) doubles as the spec for the structure if you'd rather build it by hand.

---

## Adding things

### Adding skills

Skills are domain knowledge files that agents load when their `description` matches the user's task. Create a flat markdown file in `.ai/skills/`:

```markdown
<!-- .ai/skills/my-domain.md -->
---
name: My Domain Knowledge
description: Use when working on [domain]. Do NOT use for [anti-trigger].
---

## When to Use

Load this skill when working on [describe the domain].

## Key Patterns

- Pattern 1: description
- Pattern 2: description
```

After running sync, this becomes available as:

| Tool | Location | Discovery |
|------|----------|-----------|
| Claude Code | `.claude/skills/my-domain/SKILL.md` | Automatic — Claude sees all skills in `.claude/skills/` |
| Codex | `.agents/skills/my-domain/SKILL.md` | Automatic — `/skills` lists, `$name` invokes; real files (not symlinks) so selectors discover them |
| VS Code Copilot | `.github/skills/my-domain/SKILL.md` | Referenced via `<skill>` blocks in `.github/copilot-instructions.md` |
| Cursor | `.cursor/rules/my-domain.md` | Automatic if present in `.cursor/rules/` (see [Cursor compatibility](#cursor-compatibility)) |

**Tip for Copilot**: list your skills in `.ai/project.md` so the composed `.github/copilot-instructions.md` references them — Copilot loads skills on-demand when its instructions point to them.

**Description quality matters more than skill content.** Front-load the trigger condition and add anti-triggers ("Do NOT use for …"). See [.ai/docs/harness-support.md](.ai/docs/harness-support.md) for details.

### Adding prompts (slash commands)

Prompts become reusable slash commands you can invoke in chat. The repo already ships one — [.ai/prompts/example-command.md](.ai/prompts/example-command.md) — whose only job is to print "Hello World" with emojis. Running `/example-command` (or the harness-specific equivalent below) is the fastest way to confirm prompts are wired up end-to-end before you author your own.

Create new prompts as flat markdown files in `.ai/prompts/`:

```markdown
<!-- .ai/prompts/my-prompt.md -->
---
name: My Prompt
description: One-line description of what this prompt does.
---

Body of the prompt sent to the model when invoked.
```

After sync, `example-command` becomes available as:
- **Claude Code**: `/example-command` (reads from `.claude/skills/example-command/SKILL.md`; `.claude/commands/` is also written for CLI compatibility but deprecated)
- **Codex**: `/example-command` or `$example-command` (reads from `.agents/skills/example-command/SKILL.md` — prompts and skills are the same mechanism in Codex)
- **VS Code Copilot**: `/example command` (reads from `.github/prompts/example-command.prompt.md`)
- **Gemini CLI**: `/run:example-command` (reads from `.gemini/commands/run/example-command.toml`, converted to TOML by the sync; the `run:` namespace avoids collision with `/skill example-command` which Gemini auto-discovers from `.agents/skills/`; run `/commands reload` to pick up changes)

> **Note**: Claude Code uses the **filename** as the command name. VS Code Copilot uses the **`name` field** from YAML frontmatter. Keep both sensible.

### Adding MCP servers

Create `.ai/mcp-servers.json` with your MCP server definitions:

```json
{
  "mcpServers": {
    "my-docs-server": {
      "command": "node",
      "args": ["path/to/server.js"],
      "env": {}
    }
  }
}
```

The sync fans this out to every harness:

| Target | Harness | How |
|---|---|---|
| `.mcp.json` (repo root) | Claude Code + VS Code Copilot | Symlink — both read this format natively |
| `.codex/config.toml` | Codex | Generated TOML (`[mcp_servers.*]` tables). User-owned files (missing the `# ai-sync-generated` marker) are never overwritten |
| `.gemini/settings.json` | Gemini CLI | **Merged** under the `mcpServers` key — other settings and user-added servers with different names are preserved; same-named servers are authoritative from `.ai/` |

Gemini also supports extra per-server fields (`trust`, `includeTools`/`excludeTools`, `timeout`, `url`/`httpUrl` transports) — these pass through the merge untouched. See [.ai/docs/harness-support.md](.ai/docs/harness-support.md) for details and [.ai/docs/test-instructions.md](.ai/docs/test-instructions.md) for how to verify each harness sees the servers.

---

## How the Sync Script Works

The sync engine ([.ai/scripts/sync.js](.ai/scripts/sync.js)) is a zero-dependency Node.js script that:

1. **Creates directories** needed by each tool (`.claude/skills/`, `.github/prompts/`, `.agents/skills/`, `.codex/`, etc.)
2. **Composes agent instructions** — concatenates `.ai/project.md` + `.ai/base.md` and writes the result to `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md`, and `.agents/context/AGENTS.md`
3. **Links skills** — for each `.ai/skills/<name>.md`, creates a symlink at `.claude/skills/<name>/SKILL.md` and `.github/skills/<name>/SKILL.md`, and a real file copy at `.agents/skills/<name>/SKILL.md` (Codex skill selectors don't follow symlinks reliably)
4. **Links prompts** — for each `.ai/prompts/<name>.md`, creates entries at `.claude/skills/<name>/SKILL.md`, `.agents/skills/<name>/SKILL.md`, `.github/prompts/<name>.prompt.md`, `.gemini/commands/run/<name>.toml` (TOML-converted; namespaced under `run/` so `/run:<name>` doesn't collide with Gemini's auto-discovered `/skill <name>`), and `.claude/commands/<name>.md` (deprecated, kept for CLI compatibility)
5. **Syncs MCP config** — symlinks `.ai/mcp-servers.json` → `.mcp.json`, generates `.codex/config.toml`, and merges into `.gemini/settings.json`
6. **Cleans stale links** — removes symlinks for skills/prompts you've deleted from `.ai/`

### Symlink vs. copy

- **macOS / Windows with Developer Mode**: uses symlinks (zero overhead, live updates)
- **Windows without Developer Mode**: falls back to file copies with a hash manifest (`.ai/.sync-manifest.json`) for drift detection

### Safety guardrails

- Never overwrites human-created files — only replaces symlinks and copies whose hash matches the manifest
- If you manually create a file at a generated path, it's treated as a local override and preserved

---

## When the Sync Runs (Automatic Triggers)

The sync is designed to run automatically at key moments so you never have stale generated files:

| Trigger | Config file | When it fires |
|---------|-------------|---------------|
| **VS Code workspace open** | `.vscode/tasks.json` | Every time you open the workspace in VS Code. Uses `"runOn": "folderOpen"`. First time requires clicking "Allow Automatic Tasks" in the notification. |
| **Git pull / merge** | `.githooks/post-merge` | After every `git pull` or `git merge` brings in changes. |
| **Git checkout** | `.githooks/post-checkout` | After switching branches or checking out commits. |
| **npm install** | `package.json` `"postinstall"` | Runs automatically after `npm install`. |
| **Manual** | — | `node .ai/scripts/sync.js` or `npm run ai-sync` |
| **Watch mode** | — | `node .ai/scripts/sync.js --watch` — live-reloads during authoring sessions |

### Enabling git hooks

Git hooks require a one-time setup per clone:

```bash
git config core.hooksPath .githooks
```

The `.gitattributes` file ensures LF line endings on hooks so they work on Windows (Git for Windows runs them with its bundled `sh.exe`).

### Enabling VS Code auto-task

The first time VS Code sees the `"runOn": "folderOpen"` task, it shows a notification asking to allow automatic tasks. Click **Allow** once and it runs silently on every future workspace open.

---

## Cursor Compatibility

Cursor reads from `.cursor/rules/` for project rules. The sync script doesn't generate Cursor files by default, but you have options:

1. **Manual symlink** (recommended if using Cursor):
   ```bash
   # Link your skills into Cursor's rules directory
   mklink /D .cursor\rules .ai\skills   # Windows
   ln -s .ai/skills .cursor/rules       # macOS/Linux
   ```

2. **Cursor reads `AGENTS.md`** at the repo root, which the sync already generates from your `.ai/project.md` + `.ai/base.md`.

3. **Add Cursor targets to sync.js** — extend the `skillTargets` or add a new section if you want full automation.

---

## Authoring Convention: Root-Relative Links

All cross-references in `.ai/` source files (including this README) must use **root-relative paths**:

```markdown
See [.ai/docs/harness-support.md](.ai/docs/harness-support.md) and
[.ai/skills/my-skill.md](.ai/skills/my-skill.md).
```

Symlinks resolve relative paths from the *link's* location, not the source file's. Root-relative links work from both `AGENTS.md` (at the repo root) and `.github/copilot-instructions.md` (one level deep). They may appear broken when browsing inside `.ai/` in an editor — that's expected.

---

## Project Structure

```
├── .ai/                          ← Source of truth (this folder)
│   ├── README.md                 ← You are here
│   ├── project.md                ← Project-specific agent instructions
│   ├── base.md                   ← Portable base instructions (reuse across repos)
│   ├── mcp-servers.json          ← MCP server definitions (optional)
│   ├── scripts/sync.js           ← Sync engine (zero dependencies)
│   ├── docs/                     ← Deeper reference docs
│   │   ├── harness-support.md    ← Per-harness reference
│   │   ├── test-instructions.md  ← Verification steps
│   │   └── setup-plan.md         ← Historical design notes
│   ├── skills/                   ← Domain knowledge (flat .md files)
│   │   └── validate-harness-sync.md
│   └── prompts/                  ← Slash commands (flat .md files)
│       ├── example-command.md
│       ├── harness-setup.md
│       └── update-docs.md
├── .githooks/                    ← Git hooks (auto-sync on pull/checkout)
│   ├── post-merge
│   └── post-checkout
├── .vscode/tasks.json            ← VS Code auto-sync on workspace open
├── README.md                     ← Thin stub pointing into .ai/
├── package.json                  ← npm aliases (ai-sync, ai-watch, postinstall)
├── .gitignore                    ← Ignores all generated targets
└── .gitattributes                ← LF line endings for git hooks
```

### Generated (gitignored) outputs

```
├── AGENTS.md                     ← Read by Codex, Cursor, Amp, generic agents
├── CLAUDE.md                     ← Read by Claude Code
├── GEMINI.md                     ← Read by Gemini CLI
├── .mcp.json                     ← Read by Claude Code + VS Code Copilot
├── .codex/
│   └── config.toml               ← Codex MCP servers (generated TOML)
├── .gemini/
│   ├── settings.json             ← Gemini CLI MCP servers (merged, not overwritten)
│   └── commands/run/<name>.toml  ← Gemini CLI custom slash commands (invoked as /run:name)
├── .agents/
│   ├── context/AGENTS.md         ← Codex .agents/ context layout
│   └── skills/<name>/SKILL.md    ← Codex skills + prompts (real files, run sync after clone)
├── .github/
│   ├── copilot-instructions.md   ← Read by VS Code Copilot
│   ├── prompts/<name>.prompt.md  ← Copilot slash commands
│   └── skills/<name>/SKILL.md    ← Copilot skills
└── .claude/
    ├── commands/<name>.md        ← Claude Code slash commands (deprecated location)
    └── skills/<name>/SKILL.md    ← Claude Code skills + prompts
```

---

## Design Principles

- **Vendor-agnostic**: One source, many targets. No lock-in.
- **Zero dependencies**: Plain Node.js — no npm install required for the sync itself.
- **Progressive disclosure**: Short root map → detailed docs via links.
- **Safe**: Never overwrites human files. Symlink or hash-verified copies only.
- **Cross-platform**: Identical behavior on macOS and Windows.

## Credits

- Authored by @cacheflowe
- Adapted from the [Harness Engineering](https://openai.com/index/harness-engineering/) approach to AI-assisted development.
