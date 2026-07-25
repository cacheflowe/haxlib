# `.ai/` — Cross-Harness Agent Configuration

This folder is the **source of truth** for AI agent context across Claude Code, OpenAI Codex, VS Code Copilot, Antigravity CLI, Cursor, and others. A zero-dependency Node.js sync script in [.ai/scripts/sync.js](.ai/scripts/sync.js) fans these source files out to every harness's expected paths so you author once and every tool sees the same instructions.

`sync.js` is module-mode safe: it runs in projects with or without `"type": "module"` in `package.json`.

If you've just dropped `.ai/` into a new project, start with the [Quickstart](#quickstart) below. If you're trying to add a skill, prompt, or MCP server, jump to [Adding things](#adding-things).

You can find the latest version of this project at https://github.com/Hovercraft-Studio/agents-config-sync

---

## What you edit vs. what's generated

The harness only works if you stay on the right side of this line.

### Edit these (sources)

| Path | Purpose |
|---|---|
| `.ai/AGENTS.md` | Project-specific agent instructions (what *this* repo is, key dirs, project doc links) |
| `.ai/mcp-servers.json` | MCP server definitions (ships pre-wired to `@modelcontextprotocol/server-everything` for smoke-testing — delete or replace once you add real servers) |
| `.ai/skills/<name>.md` | Domain knowledge agents load when relevant |
| `.ai/prompts/<name>.md` | Slash commands you invoke explicitly |

### Don't edit these (harness internals)

These ship with the harness and are maintained by the agents-config-sync project. Touch them only if you're upstreaming improvements to the harness itself — adopters should leave them alone so they can pull future updates cleanly.

| Path | Why |
|---|---|
| `.ai/scripts/sync.js` | Sync engine — only modify if extending sync behavior |
| `.ai/.sync-manifest.json` | Generated state; regenerated on every sync |
| `.ai/docs/*.md` | Harness reference docs (per-harness support, test instructions, setup notes) |
| `.ai/_base.md` | Instructions regarding how the harness sync works |
| `.ai/README.md` | This file — documents the harness itself |

### Never edit these (generated harness targets)

These are produced from `.ai/` sources on every sync. They are **gitignored** and any direct edits will be overwritten.

| Path | Harness |
|---|---|
| `CLAUDE.md`, `AGENTS.md` | Claude Code; Codex + Antigravity CLI (both read `AGENTS.md`) |
| `.github/copilot-instructions.md` | VS Code Copilot |
| `.agents/context/AGENTS.md` | Codex / Antigravity `.agents/` layout |
| `.claude/skills/<name>/SKILL.md` | Claude Code skills + prompts |
| `.claude/commands/<name>.md` | Claude Code commands (deprecated location, still written for CLI compat) |
| `.agents/skills/<name>/SKILL.md` | Codex + Antigravity skills + prompts (real file copies — Codex selectors don't follow symlinks) |
| `.agents/mcp_config.json` | Antigravity CLI MCP servers (generated JSON, `serverUrl` schema) |
| `.github/skills/<name>/SKILL.md` | Copilot skills |
| `.github/prompts/<name>.prompt.md` | Copilot prompts |
| `.mcp.json` | Claude Code + Copilot MCP config (symlink to `.ai/mcp-servers.json`) |
| `.pi/mcp.json` | `.pi` agent harness MCP config (symlink to `.ai/mcp-servers.json`) |
| `.codex/config.toml` | Codex MCP config (generated TOML) |

Whenever you change a source, run `node .ai/scripts/sync.js` (or let one of the [automatic triggers](#when-the-sync-runs-automatic-triggers) handle it).

---

## Quickstart

**Copy these files/folders from agents-config-sync to your target project:**

### Step 1: Copy the core toolkit

| Source | Target | Notes |
|--------|--------|-------|
| `.ai/` | `<your-project>/.ai/` | **Copy the entire directory.** This is the source of truth. |
| `.githooks/` | `<your-project>/.githooks/` | Optional. Git hooks auto-sync on pull/checkout. |
| `.gitattributes` | `<your-project>/.gitattributes` | Optional. If your project already has this, merge the entries. |

```bash
# PowerShell
Copy-Item ".ai" -Destination "<your-project>/.ai" -Recurse
Copy-Item ".githooks" -Destination "<your-project>/.githooks" -Recurse

# macOS/Linux bash
cp -r .ai <your-project>/.ai
cp -r .githooks <your-project>/.githooks
```

### Step 2: Merge these files into your project

| Source | Target | What to do |
|--------|--------|-----------|
| `.gitignore` | `<your-project>/.gitignore` | Find the `# Cross-AI Tooling` comment in agents-config-sync and copy that entire block (through `.ai/mcp-servers.json`) into your `.gitignore`. |
| `package.json` | `<your-project>/package.json` | Copy the `scripts` block: `"ai-sync": "node .ai/scripts/sync.js"` and `"ai-watch": "node .ai/scripts/sync.js --watch"`. Add `"postinstall": "node .ai/scripts/sync.js"` if not present. |
| `.vscode/tasks.json` | `<your-project>/.vscode/tasks.json` | Create or update with the `ai-sync` task below (create `.vscode/` folder if needed). |

**Add this task to `.vscode/tasks.json`:**
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

### Step 3: (Optional) Move existing instructions

If your project already has `CLAUDE.md`, `AGENTS.md`, or `.github/copilot-instructions.md`, move that content into `.ai/AGENTS.md` (for project-specific stuff) and keep `.ai/_base.md` as the portable template. Then delete the old files — the sync will regenerate them.

### Step 4: Run the sync

```bash
node .ai/scripts/sync.js
```

Or if you already have Node installed and are running npm anyway:
```bash
npm install  # postinstall hook runs sync automatically
```

> **Gitignore note**: The generated files (`CLAUDE.md`, `AGENTS.md`, `.github/copilot-instructions.md`, etc.) are gitignored. Teammates need to run `node .ai/scripts/sync.js` (or `npm install`) after cloning to regenerate them.

### Step 5: (Optional) Enable git hooks

If you copied `.githooks/`:
```bash
git config core.hooksPath .githooks
```

This auto-syncs whenever you `git pull` or `git checkout`.

### Step 6: Verify it works

Ask any agent: **"Is my agent harness set up correctly?"**

The [validate-harness-sync](.ai/skills/validate-harness-sync.md) skill will load and produce a PASS/FAIL report. Or follow the manual checklist in [.ai/docs/test-instructions.md](.ai/docs/test-instructions.md).

### Step 7: (Recommended) Set up docs tree

Run `/harness-docs-setup` in any agent (Claude Code, Copilot, Codex, Antigravity CLI). This creates an opinionated docs structure (`ARCHITECTURE.md`, `COMMANDS.md`, `DESIGN.md`, etc.) that gives agents deep, navigable context.

See [.ai/prompts/harness-docs-setup.md](.ai/prompts/harness-docs-setup.md) for details, or build it by hand using that prompt's spec.

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
| Codex / Antigravity CLI | `.agents/skills/my-domain/SKILL.md` | Automatic — both read the same `.agents/skills/` tree; real files (not symlinks) so selectors discover them |
| VS Code Copilot | `.github/skills/my-domain/SKILL.md` | Referenced via `<skill>` blocks in `.github/copilot-instructions.md` |
| Cursor | `.cursor/rules/my-domain.md` | Automatic if present in `.cursor/rules/` (see [Cursor compatibility](#cursor-compatibility)) |

**Skills, prompts & docs index is auto-generated.** Every time sync runs, it reads `.ai/skills/`, `.ai/prompts/`, and the project's `docs/` folder (recursive) and builds an index section (link + description per file) that is injected between `.ai/AGENTS.md` and `.ai/_base.md` in every composed output (`CLAUDE.md`, `AGENTS.md`, etc.). The index also lists MCP servers from `.ai/mcp-servers.json` so agents know which tool servers to expect (add an optional `description` key per server for a friendlier entry; otherwise the launch command or URL is shown). Descriptions come from frontmatter; docs without frontmatter fall back to their first `# ` heading. The source files are never modified and there are no marker comments to maintain — just add your file and run sync. Note: `--watch` mode only watches `.ai/`, so edits under `docs/` are picked up on the next sync run (git hooks and folder opens trigger one automatically).

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
- **Codex / Antigravity CLI**: `/example-command` or `$example-command` (both read from `.agents/skills/example-command/SKILL.md` — prompts and skills share the same mechanism)
- **VS Code Copilot**: `/example command` (reads from `.github/prompts/example-command.prompt.md`)

> **Note**: Claude Code uses the **filename** as the command name. VS Code Copilot uses the **`name` field** from YAML frontmatter. Keep both sensible.

### Adding MCP servers

The repo ships with `.ai/mcp-servers.json` pre-wired to Anthropic's reference test server, [`@modelcontextprotocol/server-everything`](https://www.npmjs.com/package/@modelcontextprotocol/server-everything):

```json
{
  "mcpServers": {
    "everything": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-everything"],
      "autoStart": true
    }
  }
}
```

This is a no-install canary — `npx -y` fetches it on first run. Use it to verify MCP wiring works in every harness (ask any agent to call the `echo` or `add` tool from the `everything` server and watch for the tool-confirmation prompt). Once your own servers are wired up, delete the `everything` entry or replace it.

Add your servers under the `mcpServers` key:

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
| `.pi/mcp.json` | `.pi` agent harness | Symlink — same source JSON, placed where `.pi` expects it |
| `.codex/config.toml` | Codex | Generated TOML (`[mcp_servers.*]` tables). User-owned files (missing the `# ai-sync-generated` marker) are never overwritten |
| `.agents/mcp_config.json` | Antigravity CLI | Generated JSON with `_ai_sync_generated: true` flag. Legacy `url`/`httpUrl` keys are auto-renamed to Antigravity's `serverUrl`. Hand-edited files (without the flag) are preserved |

> **Empty source = no generation.** When `mcpServers` is empty (or the source file is missing), the sync **skips all four destinations** and cleans up any previously-generated stubs it still owns. User-owned files at those paths are preserved. This keeps fresh repos free of empty MCP config files until you actually have servers to wire up.

See [.ai/docs/harness-support.md](.ai/docs/harness-support.md) for per-harness config details and [.ai/docs/test-instructions.md](.ai/docs/test-instructions.md) for how to verify each harness sees the servers.

---

## How the Sync Script Works

The sync engine ([.ai/scripts/sync.js](.ai/scripts/sync.js)) is a zero-dependency Node.js script that:

1. **Creates directories** needed by each tool (`.claude/skills/`, `.github/prompts/`, `.agents/skills/`, `.codex/`, etc.)
2. **Builds the skills, prompts & docs index** — generates an index section from current files in `.ai/skills/`, `.ai/prompts/`, and the project's `docs/` folder (descriptions pulled from frontmatter, falling back to the first `# ` heading for docs), plus an informational list of MCP servers from `.ai/mcp-servers.json`. Source files are never modified.
3. **Composes agent instructions** — concatenates `.ai/AGENTS.md` + the generated index + `.ai/_base.md` and writes the result to `AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md`, and `.agents/context/AGENTS.md`
4. **Links skills** — for each `.ai/skills/<name>.md`, creates a symlink at `.claude/skills/<name>/SKILL.md` and `.github/skills/<name>/SKILL.md`, and a real file copy at `.agents/skills/<name>/SKILL.md` (Codex / Antigravity skill selectors don't follow symlinks reliably)
5. **Links prompts** — for each `.ai/prompts/<name>.md`, creates entries at `.claude/skills/<name>/SKILL.md`, `.agents/skills/<name>/SKILL.md`, `.github/prompts/<name>.prompt.md`, and `.claude/commands/<name>.md` (deprecated, kept for CLI compatibility)
6. **Syncs MCP config** — symlinks `.ai/mcp-servers.json` → `.mcp.json` and `.pi/mcp.json`, generates `.codex/config.toml`, and generates `.agents/mcp_config.json` (renaming legacy `url`/`httpUrl` keys to Antigravity's `serverUrl`)
7. **Cleans stale links** — removes symlinks for skills/prompts you've deleted from `.ai/`

### Symlink vs. copy

- **macOS / Windows with Developer Mode**: uses symlinks (zero overhead, live updates)
- **Windows without Developer Mode**: falls back to file copies with a hash manifest (`.ai/.sync-manifest.json`) for drift detection

### Safety guardrails

- Never overwrites human-created files — only replaces symlinks and copies whose hash matches the manifest
- If you manually create a file at a generated path, it's treated as a local override and preserved

---

## When the Sync Runs (Automatic Triggers)

The sync is designed to run automatically behind the scenes so developers never have to worry about stale generated files or manual setup. This "magic" is handled by the following lifecycle triggers:


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

2. **Cursor reads `AGENTS.md`** at the repo root, which the sync already generates from your `.ai/AGENTS.md` + `.ai/_base.md`.

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
│   ├── AGENTS.md                 ← Project-specific agent instructions (skills/prompts index injected at sync time)
│   ├── _base.md                  ← Portable toolkit instructions (do not edit as adopter)
│   ├── mcp-servers.json          ← MCP server definitions (optional)
│   ├── scripts/sync.js           ← Sync engine (zero dependencies)
│   ├── docs/                     ← Deeper reference docs
│   │   ├── harness-support.md    ← Per-harness reference
│   │   ├── test-instructions.md  ← Verification steps
│   │   └── how-it-works.md       ← Architecture & design rationale
│   ├── skills/                   ← Domain knowledge (flat .md files)
│   │   └── validate-harness-sync.md
│   └── prompts/                  ← Slash commands (flat .md files)
│       ├── example-command.md
│       ├── harness-docs-setup.md
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
├── AGENTS.md                     ← Read by Codex, Antigravity CLI, Cursor, Amp, generic agents
├── CLAUDE.md                     ← Read by Claude Code
├── .mcp.json                     ← Read by Claude Code + VS Code Copilot
├── .codex/
│   └── config.toml               ← Codex MCP servers (generated TOML)
├── .agents/
│   ├── context/AGENTS.md         ← Codex / Antigravity .agents/ context layout
│   ├── mcp_config.json           ← Antigravity CLI MCP servers (serverUrl schema)
│   └── skills/<name>/SKILL.md    ← Codex + Antigravity skills + prompts (real files, run sync after clone)
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
