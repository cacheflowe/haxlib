---
name: td-ai-assisted-coding
description: Setup guide for AI coding tools in TouchDesigner projects — VS Code IntelliSense via TDI_Library, skills/prompts usage, and td-docs-mcp server configuration. Use when configuring Copilot, Claude Code, or MCP tooling for TD development.
---

# AI coding tools in TouchDesigner

- [.ai/skills/td-skills.md](.ai/skills/td-skills.md) — TouchDesigner-specific coding context and best practices
- [.ai/prompts](.ai/prompts) — Chat prompts for various coding tasks (cleanup, refactor, etc). Triggered via `/python-cleanup` etc in Copilot chat
- [to-docs-mcp](.mcp.json) — Points to [td-docs-mcp](https://github.com/cacheflowe/td-docs-mcp) config for generating TD docs with AI assistance. MCP tools can be directly encouraged/referenced in a VS Code chat by typing `#td-docs-mcp`

## Python / VS Code setup

Use **[TDI_Library](https://derivative.ca/UserGuide/TDI_Library)** by adding `.vscode/settings.json`. This is a huge boost for Python IntelliSense, providing type hints and docstrings for TD's Python API. You can also add any other relevant settings here, e.g. for formatting. Here's an example with TDI_Library and some basic editor settings:

```json
{
  "python.defaultInterpreterPath": "C:\\Program Files\\Derivative\\TouchDesigner\\bin\\python.exe",
  "editor.insertSpaces": false,
  "editor.tabSize": 4
}
```

For more advanced Python development and the full `haxlib` setup, follow the instructions in [docs/VSCODE_PYTHON_SETUP.md](docs/VSCODE_PYTHON_SETUP.md).

## Skills and prompts

The [.ai/skills/td-skills.md](.ai/skills/td-skills.md) file contains TD-specific coding context and best practices that can be referenced in AI prompts. The [.ai/prompts](.ai/prompts) directory contains example chat prompts for various coding tasks (cleanup, refactor, etc). You can trigger these in Copilot chat by typing the corresponding command, e.g. `/python-cleanup` to trigger the Python cleanup prompt.

## MCP server configuration

Add `td-docs-mcp` for AI-assisted TD documentation context. You'll need to pull [td-docs-mcp](https://github.com/cacheflowe/td-docs-mcp) locally and point to it for Copilot & Claude, which can share the `/.mcp.json` config. Copilot traditionally lives at `.vscode/mcp.json` with the `servers` key, but I like the shared file support:

```json
{
  "mcpServers": {
    "td-docs-mcp": {
      "type": "stdio",
      "command": "uv",
      "args": ["--directory", "D:\\workspace\\td-docs-mcp\\", "run", "td-docs-mcp"],
      "autoStart": true
    }
  }
}
```

You'll know if the MCP server is running...

> In Copilot if you see autocomplete: `#td-docs-mcp` or if you click the "Configure Tools" button and see `td-docs-mcp` listed as "Running" under "My Tools". You can then use `#td-docs-mcp` in your prompt to reference it, e.g. `#td-docs-mcp what is a scriptTOP?`. Any chat should automatically trigger the tool if you ask a question relevant to the TD docs, but you can also explicitly reference it with the `#` syntax to ensure it runs.

> And in Claude by running `/mcp` and finding the `td-docs-mcp` server as "Connected" in the list of servers. You can then use `#td-docs-mcp` in your prompt to reference it, e.g. `#td-docs-mcp what is a scriptTOP?`
