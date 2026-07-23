# haxlib — Agentic Project Guide

## TouchDesigner Documentation

A `td-docs-mcp` MCP server is configured for this project. **Always query it first** when answering questions about TD operators, parameters, or Python API — do not rely on training data alone.

Available tools:
- `mcp__td-docs-mcp__search_touchdesigner_docs` — full-text search
- `mcp__td-docs-mcp__read_operator_doc` — read a specific operator's doc page
- `mcp__td-docs-mcp__get_python_class` — look up a Python class (e.g. `td.OP`, `td.CHOP`)
- `mcp__td-docs-mcp__list_categories` — list operator categories

## Project Skills & Docs

Detailed guidance lives in `.ai/skills/` and `docs/`. Reference these before writing code:

### Architecture
- [.ai/skills/td-appstore.md](.ai/skills/td-appstore.md) — AppStore state management: API, reactivity, WebSocket sync, persistence
- [.ai/skills/td-startup.md](.ai/skills/td-startup.md) — boot order, Bootstrap config load priorities, known issues
- [.ai/skills/td-oop.md](.ai/skills/td-oop.md) — OOP architecture patterns: COMP as class, extensions, replicators

### Python
- [.ai/skills/td-skills.md](.ai/skills/td-skills.md) — meta-skill: TD philosophy, Python standards, doc retrieval strategy
- [.ai/skills/td-common-mistakes.md](.ai/skills/td-common-mistakes.md) — **read this first** — 12 common hallucination traps (importing td, inventing param names, .val vs .eval(), threading rules, etc.)
- [.ai/skills/td-python.md](.ai/skills/td-python.md) — globals, types, naming, extension pattern
- [.ai/skills/td-python-style.md](.ai/skills/td-python-style.md) — PascalCase/snake_case, tabs, f-strings, Google docstrings, logging prefix pattern
- [.ai/skills/td-python-patterns.md](.ai/skills/td-python-patterns.md) — operator creation/wiring, DAT/CHOP/TOP/SOP access patterns
- [.ai/skills/td-extension-template.md](.ai/skills/td-extension-template.md) — full extension template with TDF.createProperty, StorageManager, lifecycle methods
- [.ai/skills/td-advanced-python.md](.ai/skills/td-advanced-python.md) — pattern matching, pywin32, MOD class, external module installation

### Threading & Async
- [.ai/skills/td-threading.md](.ai/skills/td-threading.md) — queue-based threading, subprocess, strict rules (never access op() from a thread)
- [.ai/skills/td-delayed-calls.md](.ai/skills/td-delayed-calls.md) — `run()` patterns, delayFrames/delayMilliSeconds, lambda from extensions

### GLSL
- [.ai/skills/td-glsl.md](.ai/skills/td-glsl.md) — best practices, built-in uniforms, noise, HSV, aspect ratio, compute shaders
- [.ai/skills/td-glsl-2.md](.ai/skills/td-glsl-2.md) — samplers, multiple color buffers, POP attributes, 3D textures

### Replicators & Wiring
- [.ai/skills/td-replicator.md](.ai/skills/td-replicator.md) — onReplicate callback, layout anchoring, clone sync
- [.ai/skills/td-wiring.md](.ai/skills/td-wiring.md) — programmatic node wiring, Connector class, setInputs

### Live Project Access (HTTP Bridge)
- [.ai/skills/td-http-api.md](.ai/skills/td-http-api.md) — **required reading** — HTTP bridge routes (`/network`, `/create`, `/par`, `/pars`, `/opinfo`, `/run`, etc.), friction points, best practices for avoiding round-trip guessing, template system
- [.ai/prompts/td-agent-init.md](.ai/prompts/td-agent-init.md) — orientation checklist when starting work on a live project

### Python Environment
- [docs/PYTHON_ENVIRONMENT.md](docs/PYTHON_ENVIRONMENT.md) — Conda (Python 3.11), venv, pipreqs, custom import patterns
- [.ai/skills/td-python-environment.md](.ai/skills/td-python-environment.md) — tdPyEnvManager, DAT-as-module imports, TD install paths
- [docs/VSCODE_PYTHON_SETUP.md](docs/VSCODE_PYTHON_SETUP.md) — VS Code Pylance config, .venv, extraPaths, module reloading

### Machine Learning
- [.ai/skills/td-ml.md](.ai/skills/td-ml.md) — ONNX Runtime 1.17 GPU, PyTorch CUDA, curated model sources

### Web UI
- [.ai/skills/web-components.md](.ai/skills/web-components.md) — vanilla JS only, AppStoreElement vs HTMLElement, Shadow DOM
- [.ai/skills/picocss-customization.md](.ai/skills/picocss-customization.md) — Pico CSS color variables, light/dark scheme

### General Reference
- [.ai/skills/td-notes.md](.ai/skills/td-notes.md) — comprehensive cheatsheet: navigation, parameter tricks, compositing, optimization
- [docs/TUTORIALS.md](docs/TUTORIALS.md) — curated learning resources, YouTube channels, community repos
- [.ai/skills/td-snippets.md](.ai/skills/td-snippets.md) — quick utility snippets
- [.ai/skills/python-string-formatting.md](.ai/skills/python-string-formatting.md) — f-string formatting reference

## Documentation Maintenance

The `docs/` folder and `.ai/skills/` are the project's living knowledge base. **When changing code behavior, always update the corresponding file in `docs/` or `.ai/skills/`.** This includes:
- New features or APIs → add or update the relevant skill or doc
- Renamed concepts or operators → fix references across skills and docs
- Deprecated patterns → mark them in the relevant file
- Bug fixes that change documented behavior → update the doc

If no relevant file exists yet, create one in `.ai/skills/` (prefer skills for TD-specific knowledge) or `docs/` (for setup guides, environment config). Files should stay accurate enough that an agent (or human) can rely on them without reading the code.

---

## Code Style Summary

- **Indentation**: tabs (not spaces)
- **Naming**: PascalCase for classes/extensions, snake_case for functions/variables, UPPER_CASE for constants
- **Strings**: f-strings preferred
- **Logging**: bracketed prefix pattern, e.g. `print(f'[MyExt] message')`
- **Docstrings**: Google format, one short line max for internal methods
- **Comments**: only when the WHY is non-obvious
