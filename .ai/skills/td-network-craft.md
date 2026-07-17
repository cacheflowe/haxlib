---
name: td-network-craft
description: Learning and applying idiomatic TouchDesigner network-building technique from the official OP Snippets corpus (1386 curated examples) plus td-docs-mcp, using the td_http_api HTTP tooling to inspect, rebuild, and verify. Use when building non-trivial networks, choosing operators, or trying to work the "TD way" rather than mechanically.
---

# TouchDesigner network craft

This skill is the home for accumulated **technique** — how to build TD networks well, not just how to operate the [td_http_api](.ai/skills/td-http-api.md) tooling mechanically. It exists because an agent has broad TD *API* knowledge (via `td-docs-mcp`) but lacks the *craft* an experienced TD artist has: which operator to reach for, idiomatic wiring, companion nodes, layout, gotchas. Since an agent doesn't persist between sessions, all such craft has to live in repo artifacts — this doc, the catalog below, and captured templates/notes.

## Primary source: OP Snippets

Derivative ships **OP Snippets** — 1386 curated, live example networks across 475 operator types, each demonstrating idiomatic use of one operator and each self-documenting via a `readMe`/`text` description. This is the single best corpus for learning "how nodes work well together," and it pairs 1:1 with the reference docs in `td-docs-mcp` (spec) — snippet = practice, doc = spec.

### How the corpus was located (for future reference)

Found by exploring TD's filesystem from inside TD via `POST /run`:

- Install root: `os.path.dirname(app.binFolder)` → e.g. `C:/Program Files/Derivative/TouchDesigner`.
- The snippets live under `Samples/Learn/OPSnippets/` as **`OPSnippetsOnDemand.tox`** — a ~382KB *loader/browser*, **not** the snippets themselves. The sibling `Snippets/` cache dir is empty until examples are requested.
- Loading that tox into a throwaway COMP (`baseCOMP.loadTox(...)`) reveals its internals: per-family base COMPs (`TOP`, `CHOP`, `SOP`, …) that hold example networks on demand, a `snippetsChooser` container, and — the key asset — a master catalog table at `…/OPSnippetsOnDemand/snippetsChooser/allAlphaNumeric`.
- Individual examples are addressed by **relpath** like `TOP/feedbackTOP/example1` and loaded on demand (the chooser extension's `goToType`/`loadTypeTox`, or `op.Snippets.op(relpath)` once launched via the Help menu).

### The catalog: `data/harness/op-snippets/catalog.tsv`

The `allAlphaNumeric` table was extracted (via `/run`, writing directly to the repo) into **[data/harness/op-snippets/catalog.tsv](data/harness/op-snippets/catalog.tsv)** — 1386 rows, columns `relpath, family, optype, label, topic, text`. `text` is Derivative's own one-line description of each example (whitespace-collapsed to stay greppable; the full multi-paragraph original is always re-readable from the live snippet's `readMe` DAT when going deep).

This file is the **Tier 1 retrieval index** — offline, greppable, and it maps *technique/goal → operator → snippet relpath → description* without loading a single network. E.g. `grep -i feedbackTOP data/harness/op-snippets/catalog.tsv` surfaces every feedback example and what each shows.

To regenerate (e.g. after a TD update): load `OPSnippetsOnDemand.tox` into a temp COMP, read `snippetsChooser/allAlphaNumeric`, write the columns out, destroy the temp COMP. It's derived reference data, not authoritative — refresh freely.

## The two-tier learning model

**Tier 1 — broad & cheap (the catalog + docs).** For "which operator, used how" questions: grep the catalog for the goal/operator, read the matching `text`, cross-reference the operator's `td-docs-mcp` doc. Covers most questions with zero network materialization.

**Tier 2 — deep & verified (per technique, on demand).** When a technique genuinely matters, materialize and study the actual snippet, then **prove understanding by rebuilding it and confirming the output matches**. A takeaway is only "solid" once it survives that rebuild. Expensive, so do it JIT (when a real task needs it) plus a small foundational seed — never a 1386-wide batch grind.

### Tier 2 per-snippet procedure

1. Locate via the catalog (`relpath`, `optype`).
2. Materialize the snippet network (drive the on-demand loader for that `optype`), then `GET /network?recursive=true` on it for structure.
3. Read every `readMe` DAT via `GET /dat` — the author's intent, highest-value signal.
4. `GET /snapshot` key TOPs, `GET /chop` key CHOPs — capture what it actually produces.
5. Pull the operator's `td-docs-mcp` doc; reconcile practice against spec. Flag unverified claims per the repo's source-accuracy rule — don't invent rationale the sources don't state.
6. **Validate by rebuild**: recreate the pattern from scratch via the write routes into a scratch COMP, then `POST /diff` the structure and snapshot-compare the output against the original. Match → promoted from "observed" to "verified"; the rebuild *is* the template.
7. Persist: template → `data/harness/network-templates/`, craft note → this doc (or a family-split doc as it grows), and it becomes reusable via `POST /create-from-template`.

This is the same analyze→build→verify loop first proven on `/project1/Demo_Feedback`, now run against Derivative's own curated corpus. Every tool built for `td_http_api` (`/snapshot`, `/chop`, `/diff`, `/errors`, template capture/instantiate) exists to make step 6's verification trustworthy.

## Open question / risk

"OnDemand" + an empty `Snippets/` cache + a tiny loader strongly implies individual example *networks* are fetched from Derivative's servers on first request. The **catalog is confirmed local and offline**; Tier-2 materialization may depend on network access and be slower/gated. Unconfirmed until a first materialization is attempted — that's the next validation step and the natural Tier-2 pilot.

## Verified craft notes

*(Accumulates here as Tier-2 investigations complete. Empty until the first pilot.)*

## See Also

- [.ai/skills/td-http-api.md](.ai/skills/td-http-api.md) — the HTTP tooling every step here relies on (`/network`, `/dat`, `/snapshot`, `/chop`, `/diff`, `/create`, `/run`, template routes).
- [data/harness/network-templates/](data/harness/network-templates/) — where verified Tier-2 rebuilds are captured as reusable templates.
