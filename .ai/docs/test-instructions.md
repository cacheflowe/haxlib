# Testing the Agent Harness

How to verify that commands, skills, MCP servers, and the shared context files
(`AGENTS.md` / `CLAUDE.md` / `.github/copilot-instructions.md`) are actually
visible to each harness: **Claude Code**, **GitHub Copilot**, and **Codex**.

## 0. Prerequisite: run the sync

All generated files come from `.ai/` sources. Before testing anything, regenerate:

```sh
node .ai/scripts/sync.js
```

Then confirm the generated targets exist:

| Check | Path |
|---|---|
| Claude Code context | `CLAUDE.md` (root) |
| Codex / generic context | `AGENTS.md` (root) |
| Gemini context | `GEMINI.md` (root) |
| Copilot context | `.github/copilot-instructions.md` |
| Claude Code skills/commands | `.claude/skills/<name>/SKILL.md` |
| Copilot skills | `.github/skills/<name>/SKILL.md` |
| Copilot prompts | `.github/prompts/<name>.prompt.md` |
| Gemini CLI commands | `.gemini/commands/run/<name>.toml` (invoked as `/run:<name>`) |
| Codex skills | `.agents/skills/<name>/SKILL.md` (gitignored — exists only after sync) |

If a target is missing, the harness can't see it — fix the sync before debugging
the harness.

## 1. Testing slash commands / prompts

The repo ships a canary prompt for exactly this purpose:
[.ai/prompts/example-command.md](.ai/prompts/example-command.md) — its only job is to print
"Hello World" with emojis, so you can tell at a glance whether the command was
*actually loaded* or the model just improvised.

**Invocation syntax varies by surface:**

- CLI tools (Claude Code CLI, Codex CLI, Copilot CLI) generally use `/name`.
- All three CLIs also support a `/skills` command (each in a slightly
  different form) that lists the skills the harness has discovered. This is
  the quickest way to confirm each CLI can see the skills synced/symlinked
  into its agent directory (`.claude/skills/`, `.agents/skills/`,
  `.github/skills/`) — if a skill is missing from the list, the sync or
  symlink is the problem, not the skill content.
- Codex additionally supports `$name` to mention a skill directly in a message.
- IDE chat windows (Copilot Chat, Claude Code extension) often have weaker or
  slower skill autocomplete than the CLIs — a skill that doesn't show up in
  the `/` dropdown may still work when typed in full. Don't conclude a skill
  is broken from autocomplete alone; type the full command and check the
  output, or verify in the CLI.

### Claude Code

1. Type `/` in the chat input. `example-command` should appear in the list.
2. Run `/example-command`. Expected output: "Hello World" with emojis.
3. If it's not listed: check `.claude/skills/example-command/SKILL.md` exists and has
   valid `name` + `description` frontmatter, then restart the session
   (skills are indexed at startup).

### GitHub Copilot (VS Code)

1. Type `/` in Copilot Chat. `example-command` should appear (sourced from
   `.github/prompts/example-command.prompt.md`).
2. Run it and confirm the Hello World output.
3. If missing: check that prompt files are enabled
   (`chat.promptFiles` setting) and reload the window.

### Codex

1. Type `/skills` to list, or `$example-command` to invoke directly.
2. If missing: run the sync (`.agents/skills/` is gitignored and must be
   regenerated after every clone), and confirm the project is trusted.

### Gemini CLI

1. Run `/commands list` — `run:example-command` should appear (sourced from
   `.gemini/commands/run/example-command.toml`). The `run:` prefix is intentional —
   it namespaces our generated commands so they don't collide with skills
   that Gemini auto-discovers from `.agents/skills/`.
2. Run `/run:example-command` and confirm the Hello World output (one-shot
   execution).
3. For comparison, `/skill example-command` *activates* the same prompt as a skill
   (loads the full SKILL.md into context but doesn't execute) — different
   mechanism, same source file. Prefer `/run:<name>` for one-shot prompts:
   it sends the prompt body once and exits, while `/skill <name>` keeps the
   entire skill loaded across turns (more tokens, lingers in context).
4. After editing a command, run `/commands reload` to pick up changes
   without restarting the CLI.
5. If missing: confirm `.gemini/commands/run/example-command.toml` exists, starts
   with the `# ai-sync-generated` marker, and contains a `prompt` field.

## 2. Testing skills (implicit invocation)

Skills differ from commands: the agent decides to load them based on the
`description` frontmatter, without you typing a slash command.

1. Pick a skill, e.g. [.ai/skills/validate-harness-sync.md](.ai/skills/validate-harness-sync.md).
2. Ask the agent a question that matches the skill's description trigger words
   — but **don't name the skill** (for `validate-harness-sync`, try "is my
   agent harness set up correctly?" or "why isn't my new skill showing up?").
3. Ask the agent: "Which skills did you load for that answer?" or check the
   harness's tool-call log for a skill read.
4. Negative test: ask something clearly outside the skill's scope and confirm
   it does *not* load (over-triggering means the description is too broad).

If a skill never triggers implicitly, the fix is almost always the
`description` line: front-load the trigger conditions ("Use when…") and add
anti-triggers ("Do NOT use for…").

### Quick end-to-end canary: `validate-harness-sync`

The repo ships [.ai/skills/validate-harness-sync.md](.ai/skills/validate-harness-sync.md)
as both a real diagnostic *and* a self-test. A successful run proves the
agent discovered the skill, loaded its content, and acted on its
instructions — three separate links in the chain.

**Implicit invocation** (preferred — tests description-based discovery):

> "Is my agent harness set up correctly?"
> "Can you validate the harness sync in this repo?"
> "Why isn't my new skill showing up in <tool>?"

**Explicit invocation** (use if implicit doesn't trigger — isolates whether the
problem is the skill content vs. the description trigger):

- Claude Code: `/validate-harness-sync` (or type the name after `/`)
- Codex: `$validate-harness-sync`
- Copilot / Gemini: mention the skill name directly in your message

**A passing run** produces a PASS/FAIL table covering source files, composed
context files, synced skills/prompts, MCP config, and the sync manifest — see
the skill itself for the full schema. If you get a generic answer instead of
the table, the skill wasn't loaded (check that
`.claude/skills/validate-harness-sync/SKILL.md` /
`.agents/skills/validate-harness-sync/SKILL.md` /
`.github/skills/validate-harness-sync/SKILL.md` exist, then restart the
session).

## 3. Testing the shared context (AGENTS.md / CLAUDE.md / copilot-instructions.md)

Use a **canary token** to prove the file is in the agent's context, rather than
asking "did you read CLAUDE.md?" (models will often say yes regardless).

1. Add a distinctive, un-guessable line to `.ai/project.md`, e.g.:

   ```markdown
   <!-- canary: the project mascot is a purple axolotl named Reginald -->
   ```

2. Run `node .ai/scripts/sync.js` so it propagates to all generated targets.
3. Start a **fresh session** in each harness (context files load at session start).
4. Ask: *"What is the project mascot?"* — no hints, no file references.

| Harness | Expected behavior |
|---|---|
| Claude Code | Answers from `CLAUDE.md` without reading any file |
| Copilot Chat | Answers from `.github/copilot-instructions.md` (check `github.copilot.chat.codeGeneration.useInstructionFiles` is enabled) |
| Codex | Answers from root `AGENTS.md` |
| Gemini CLI | Answers from `GEMINI.md` |

5. Remove the canary and re-sync when done.

A correct answer proves the full chain: `.ai/project.md` → sync → generated
file → harness context. A wrong answer (or a file-read tool call before
answering) tells you which link is broken.

## 4. Testing MCP servers

MCP config source is `.ai/mcp-servers.json`, synced to `.mcp.json` (Claude
Code/Copilot), `.codex/config.toml` (Codex), and merged into
`.gemini/settings.json` (Gemini CLI). If `.ai/mcp-servers.json` doesn't exist
yet, there's nothing to test — see
[.ai/docs/harness-support.md](.ai/docs/harness-support.md) for config formats.

### Claude Code

1. Run `claude mcp list` in a terminal, or `/mcp` inside a session — the
   server should be listed as connected.
2. Ask the agent to use one of the server's tools and confirm a real tool
   call happens (visible in the transcript), not a hallucinated answer.
3. Project-scoped servers in `.mcp.json` require one-time approval on first
   use — watch for the prompt.

### GitHub Copilot (VS Code)

1. Open the Copilot Chat tools picker (the wrench icon) — the MCP server's
   tools should be listed.
2. Check `MCP: List Servers` in the command palette for connection status
   and logs.
3. Invoke a tool via chat and confirm the tool-call confirmation dialog
   appears.

### Codex

1. Run `codex mcp list` to confirm the server is registered.
2. Confirm `.codex/config.toml` starts with the `# ai-sync-generated` marker —
   if not, the sync script treats it as user-owned and won't update it.
3. Invoke a tool in a session and verify the call in the transcript.

### Gemini CLI

1. Confirm `.gemini/settings.json` contains your server under `mcpServers`
   after running the sync (the sync merges this key and preserves any other
   settings in the file).
2. Inside a session, run `/mcp` — each connected server should list its
   Tools, Prompts, and Resources.
3. If the server exposes resources, type `@` and confirm
   `@server://resource/path` URIs appear in the completion menu alongside
   file paths.
4. Invoke a tool and confirm the confirmation prompt appears (unless the
   server is configured with `trust: true`, which bypasses confirmations).

### Generic MCP smoke test

For any harness, the strongest test is a **round trip**: ask the agent to call
a tool whose output you can independently verify (e.g. "list the files in X
via the MCP server") and compare against ground truth.

## 5. Troubleshooting checklist

- **Stale generated files** → re-run `node .ai/scripts/sync.js`; never edit
  generated files directly.
- **Harness caches context at session start** → always restart the
  session/window after a sync before testing.
- **Skill not triggering** → tighten the `description` frontmatter; Codex
  truncates the skills list at ~8,000 characters total.
- **Copilot ignoring instructions** → confirm
  `useInstructionFiles` is enabled and the file is at
  `.github/copilot-instructions.md` exactly.
- **Codex missing skills after clone** → `.agents/skills/` is gitignored;
  run the sync.
