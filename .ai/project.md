# haxlib — Agentic Project Guide

## TouchDesigner Documentation

A `td-docs-mcp` MCP server is configured for this project. **Always query it first** when answering questions about TD operators, parameters, or Python API — do not rely on training data alone.

Available tools:
- `mcp__td-docs-mcp__search_touchdesigner_docs` — full-text search
- `mcp__td-docs-mcp__read_operator_doc` — read a specific operator's doc page
- `mcp__td-docs-mcp__get_python_class` — look up a Python class (e.g. `td.OP`, `td.CHOP`)
- `mcp__td-docs-mcp__list_categories` — list operator categories

## Project Skills & Docs

Detailed guidance lives in `.github/skills/` and `docs/`. Reference these before writing code:

### Architecture
- [docs/APPSTORE.md](docs/APPSTORE.md) — central state management (AppStore extension), three-layer storage, WebSocket sync, full API
- [docs/STARTUP_SEQUENCE.md](docs/STARTUP_SEQUENCE.md) — boot order, Bootstrap, extension init, .env loading, known issues
- [docs/OOP_IN_TD.md](docs/OOP_IN_TD.md) — COMP as class, extensions, replicators, Python-nodes-Python flow
- [.github/skills/td-oop/SKILL.md](.github/skills/td-oop/SKILL.md) — OOP architecture patterns

### Python
- [.github/skills/TD_SKILLS.md](.github/skills/TD_SKILLS.md) — meta-skill: TD philosophy, Python standards, doc retrieval strategy
- [.github/skills/td-common-mistakes/SKILL.md](.github/skills/td-common-mistakes/SKILL.md) — **read this first** — 12 common hallucination traps (importing td, inventing param names, .val vs .eval(), threading rules, etc.)
- [.github/skills/td-python/SKILL.md](.github/skills/td-python/SKILL.md) — globals, types, naming, extension pattern
- [.github/skills/td-python-style/SKILL.md](.github/skills/td-python-style/SKILL.md) — PascalCase/snake_case, tabs, f-strings, Google docstrings, logging prefix pattern
- [.github/skills/td-python-patterns/SKILL.md](.github/skills/td-python-patterns/SKILL.md) — operator creation/wiring, DAT/CHOP/TOP/SOP access patterns
- [.github/skills/td-extension-template/SKILL.md](.github/skills/td-extension-template/SKILL.md) — full extension template with TDF.createProperty, StorageManager, lifecycle methods
- [docs/PYTHON_SNIPPETS.md](docs/PYTHON_SNIPPETS.md) — Script CHOP, DAT table ops, text TOP measurement, debugging helpers
- [docs/ADVANCED_PYTHON.md](docs/ADVANCED_PYTHON.md) — pattern matching, pywin32, MOD class, external module installation

### Threading & Async
- [.github/skills/td-threading/SKILL.md](.github/skills/td-threading/SKILL.md) — queue-based threading, subprocess, strict rules (never access op() from a thread)
- [.github/skills/td-delayed-calls/SKILL.md](.github/skills/td-delayed-calls/SKILL.md) — `run()` patterns, delayFrames/delayMilliSeconds, lambda from extensions
- [docs/THREADING_OLD.md](docs/THREADING_OLD.md) — legacy threading reference

### GLSL
- [.github/skills/td-glsl/SKILL.md](.github/skills/td-glsl/SKILL.md) — best practices, built-in uniforms, noise, HSV, aspect ratio, compute shaders
- [.github/skills/td-glsl/SKILL-2.md](.github/skills/td-glsl/SKILL-2.md) — samplers, multiple color buffers, POP attributes, 3D textures

### Replicators & Wiring
- [.github/skills/td-replicator/SKILL.md](.github/skills/td-replicator/SKILL.md) — onReplicate callback, layout anchoring, clone sync
- [.github/skills/td-wiring/SKILL.md](.github/skills/td-wiring/SKILL.md) — programmatic node wiring, Connector class, setInputs

### Python Environment
- [docs/PYTHON_ENVIRONMENT.md](docs/PYTHON_ENVIRONMENT.md) — Conda (Python 3.11), venv, pipreqs, custom import patterns
- [.github/skills/td-python-environment/SKILL.md](.github/skills/td-python-environment/SKILL.md) — tdPyEnvManager, DAT-as-module imports, TD install paths
- [docs/VSCODE_PYTHON_SETUP.md](docs/VSCODE_PYTHON_SETUP.md) — VS Code Pylance config, .venv, extraPaths, module reloading

### Machine Learning
- [.github/skills/td-ml/SKILL.md](.github/skills/td-ml/SKILL.md) — ONNX Runtime 1.17 GPU, PyTorch CUDA, curated model sources
- [docs/ML_IN_TD.md](docs/ML_IN_TD.md) — CUDA/TD version compatibility, model list (depth, pose, segmentation, OCR, etc.)

### Web UI
- [.github/skills/web-components/SKILL.md](.github/skills/web-components/SKILL.md) — vanilla JS only, AppStoreElement vs HTMLElement, Shadow DOM
- [.github/skills/picocss-customization/SKILL.md](.github/skills/picocss-customization/SKILL.md) — Pico CSS color variables, light/dark scheme

### General Reference
- [docs/TD-NOTES.md](docs/TD-NOTES.md) — comprehensive cheatsheet: navigation, parameter tricks, compositing, optimization
- [docs/TUTORIALS.md](docs/TUTORIALS.md) — curated learning resources, YouTube channels, community repos
- [.github/skills/td-snippets/SKILL.md](.github/skills/td-snippets/SKILL.md) — quick utility snippets
- [.github/skills/python-string-formatting/SKILL.md](.github/skills/python-string-formatting/SKILL.md) — f-string formatting reference

## Documentation Maintenance

The `docs/` folder is the project's living knowledge base. **When changing code behavior, always update the corresponding doc in `docs/`.** This includes:
- New features or APIs → add or update the relevant doc
- Renamed concepts or operators → fix references in docs
- Deprecated patterns → mark them in the relevant doc
- Bug fixes that change documented behavior → update the doc

If no relevant doc exists yet, create one. Docs should stay accurate enough that an agent (or human) can rely on them without reading the code.

---

## Code Style Summary

- **Indentation**: tabs (not spaces)
- **Naming**: PascalCase for classes/extensions, snake_case for functions/variables, UPPER_CASE for constants
- **Strings**: f-strings preferred
- **Logging**: bracketed prefix pattern, e.g. `print(f'[MyExt] message')`
- **Docstrings**: Google format, one short line max for internal methods
- **Comments**: only when the WHY is non-obvious
