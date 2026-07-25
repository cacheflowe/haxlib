## Core Principle: Documentation is Infrastructure (if docs exist)

**If this project maintains documentation** (either `.ai/docs/`, project-level `docs/`, or both), then **harness documentation and agent context are part of your system infrastructure**. Whenever you change code, patterns, or agent behavior, update the corresponding docs in the same change—agents read these docs to understand how to behave consistently.

Use the `/update-docs` prompt to audit and fix docs after any change. The sync harness ensures all agents see the same current instructions.

**If this project has no docs**, skip this discipline. The sync harness works fine without it.

---

## How This File Works

The `.ai/` directory is the **Agents Config Sync** toolkit — the single source of truth for AI agent configuration in this repository, synced to every harness.

* **Never edit generated files directly** (`AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md`, `.agents/context/AGENTS.md`, `.mcp.json`, etc.).
* **To update context**, edit `.ai/AGENTS.md` or files under `.ai/skills/`/`.ai/prompts/` and run `node .ai/scripts/sync.js` to regenerate.
* For sync architecture details and file-mapping tables, see [.ai/docs/how-it-works.md](.ai/docs/how-it-works.md) and [.ai/README.md](.ai/README.md).

### Authoring Convention: Root-Relative Links
All cross-references inside `.ai/` source files (links to skills, docs, or other markdown) **must use root-relative paths**, e.g.:
`See [docs/systemArchitecture.md](docs/systemArchitecture.md) and [.ai/skills/code-reviewer.md](.ai/skills/code-reviewer.md).`

---

## Documentation Maintenance
* **Do not edit `.ai/docs/`**: This directory documents the sync toolkit itself. Only toolkit maintainers should update it.
* **Update your project's custom docs instead**:
  1. **`.ai/skills/`** — Domain knowledge for *this* project (APIs, patterns, workflows).
  2. **`.ai/AGENTS.md`** — Project-specific context (key dirs, style, team).
  3. **`docs/`** (at root, if present) — Living project docs (architecture, specs, guides).
  4. **`README.md`** (root) — Entry point.
* **Key principle**: Code changes that alter behavior must update the corresponding docs under `docs/` or `.ai/` in the same work.


---

## Agent Learnings Log
This project keeps a living log of hard-won coding discoveries at [`docs/learnings/`](docs/learnings/). Read it before debugging; write to it after solving anything non-obvious or that took significant effort or iterations.

**Read first when:**
- Debugging any code issues issue — check [`docs/README.md`](docs/README.md) for prior solutions before digging into source code.
- Something "should work" per the docs but doesn't — an existing entry may explain it.

**Write an entry when:**
- You fix a bug that cost real investigation time and isn't in official docs.
- You discover a pattern or failure mode specific to this stack's versions.
- Your reasoning took multiple iterations to get right, and you want to save time for future agents.
- Format: **Symptom → Root cause → Fix** + a code snippet if useful. Keep it short. Add to the most relevant file in `docs/learnings/`, or create a new topic file.

**Manage the log like code**
- Each entry is a discrete unit of knowledge. The collection is a shared resource for all agents to consult and contribute to.
- Be sure to update docs/README.md with new files or sections as the log grows.

---

## Source Accuracy & Drafting Protocol
Never fabricate statistics, data points, or claims not explicitly present in source documents. If a fact cannot be verified, flag it as `[NEEDS SOURCE]` or `[UNVERIFIED]`.
1. **Read first, write second**: Read all provided source documents fully before drafting.
2. **Maintain a source map**: Track every factual claim, metric, name, or date back to its source.
3. **Verify before delivering**: For substantive documents, check every claim against source documents and remove unverifiable claims.
4. **No invention**: Never generate statistics, quotes, or details not found in the sources.
