# haxlib

A personal toolkit for TouchDesigner software development.

## AI coding tools

- [TD_SKILLS.md](.github/skills/TD_SKILLS.md) — TouchDesigner-specific coding context and best practices
- [prompts](.github/prompts) — Chat prompts for various coding tasks (cleanup, refactor, etc). Triggered via `/python-cleanup` etc in Copilot chat
- [to-docs-mcp](.vscode/mcp.json) — Points to [td-docs-mcp](https://github.com/cacheflowe/td-docs-mcp) config for generating TD docs with AI assistance. MCP tools can be directly encouraged/referenced in a VS Code chat by typing `#td-docs-mcp`

## Python / VS Code setup

Use **TDI_Library** by adding `.vscode/settings.json`:

```json
{
  "python.defaultInterpreterPath": "C:\\Program Files\\Derivative\\TouchDesigner\\bin\\python.exe",
  "editor.insertSpaces": false,
  "editor.tabSize": 4
}
```

Add `td-docs-mcp` to `.vscode/mcp.json` for AI-assisted TD documentation context. You'll need to pull [td-docs-mcp](https://github.com/cacheflowe/td-docs-mcp) locally and point to it:

```json
{
  "servers": {
    "td-docs-mcp": {
      "type": "stdio",
      "command": "uv",
      "args": ["--directory", "D:\\workspace\\td-docs-mcp\\", "run", "td-docs-mcp"]
    }
  }
}
```

## TODO

- [WIP] Revisit AppStore init in Bootstrap
  - bring latest code over from EA (bootstrap and AppStore py/tox)
  - Had to click `force defaults` on fresh project :-/ This should just work
  - Check AppStore file backup/restore process
- Add more skills/prompts
- Bring in components from other projects
