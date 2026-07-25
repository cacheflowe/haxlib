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

To regenerate (e.g. after a TD update), prefer the self-contained bridge refresh route:

```bash
curl -X POST -d "" "http://127.0.0.1:3031/examples-refresh"
```

or with an explicit output path:

```bash
curl -X POST -d "" "http://127.0.0.1:3031/examples-refresh?output=D:/workspace/haxlib/data/harness/op-snippets/catalog.tsv"
```

You can still stream raw TSV if needed:

```bash
curl -s "http://127.0.0.1:3031/examples.tsv" > data/harness/op-snippets/catalog.tsv
```

or on PowerShell:

```powershell
curl.exe -s -o data/harness/op-snippets/catalog.tsv "http://127.0.0.1:3031/examples.tsv"
```

Both forms are derived reference data exports, not authoritative — refresh freely.

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

## Open question / risk — resolved

"OnDemand" + an empty `Snippets/` cache + a tiny loader strongly implies individual example *networks* are fetched from Derivative's servers on first request. The **catalog is confirmed local and offline**. First materialization attempted and confirmed: the individual example `.tox` files (e.g. `Samples/Learn/OPSnippets/Snippets/COMP/geometryCOMP.tox`) are **already present locally** on disk — no network fetch observed or required. Materialization is fast (a single `loadTox` call).

### How to actually materialize a specific example (verified mechanism)

The loader `.tox`'s `snippetsChooser` COMP has a `Chooser` extension (readable via `GET /dat` on its `extChooser` Text DAT) whose `loadTypeTox(family, optype)` method is the real mechanism — reverse-engineered from source, not guessed:

1. Load the loader once: `probe = parent.create(baseCOMP, '_snippet_probe'); probe.loadTox(app.binFolder's-parent + '/Samples/Learn/OPSnippets/OPSnippetsOnDemand.tox')` — this creates a child `OPSnippetsOnDemand` COMP (loadTox adds a child, it does not replace the target).
2. Get the family base COMP: `comp_base = probe_root.op('COMP')` (or `'TOP'`/`'SOP'`/etc — matches the catalog's `family` column).
3. Load the specific optype's tox directly into it: `comp_base.loadTox(app.samplesFolder + '/Learn/OPSnippets/Snippets/' + family + '/' + optype + '.tox')`. This populates `comp_base/optype` with one child per numbered example (`example1`, `example2`, …).
4. The desired example is `comp_base.op(optype).op('example' + N)` (or iterate `.children` and match `.name` — see the utility-node gotcha below).

**Do this in one atomic `/run` script**, not several round trips. The chooser has watcher `executeDAT`s (`execute_start`, `execute_cookAllExampleButtons`, etc.) that call `destroySnippets()` — which deletes everything in every family folder — when the loaded state doesn't match what the chooser's own extension thinks is selected (since we bypassed `goToType`/`goToExampleFTE`, which set that state). Confirmed live: a loaded `geometryCOMP` family folder with 5 examples was completely wiped between two separate `/run` calls, purely from that housekeeping running on a later cook. Load + inspect (or load + read + destroy) in the same script to avoid racing it.

**The loaded example COMPs (`example1`, `example2`, …, and even the family folder itself) are utility-flagged** — a global `op('/full/absolute/path/.../example2')` string lookup returns `None` even though the node visibly exists and `/network` lists it fine. Use `.op('example2')` (single-name shortcut method) chained from a real parent reference, or iterate `.children` and match `.name`, exactly like the skill's existing "Utility Node" gotcha documented elsewhere in this repo — don't fight it with `includeUtility=True` on `findChildren` for this particular case, plain `.op(name)`/`.children` already works.

**Always `.destroy()` the temp probe COMP at the end** (per probe hygiene) and verify with `op(path) is None` — confirmed working (`destroy(); print(op(path) is not None)` → `False`).

## Verified craft notes

**Instancing a Geometry COMP from CHOP channel data** (materialized `COMP/geometryCOMP/example2`, reconciled a from-scratch build against it, both live in `/project1/TESTING/InstancingDemo` (unverified first pass) and `/project1/TESTING/InstancingDemo_Verified` (matches the real snippet's technique)):

- Real pattern: a loose SOP network (a shape SOP — `grid1`/`box1`/`sphere1` in the original, switchable) feeds `sopto1` (`SOP to CHOP`, `position` toggle on → auto-creates `tx`/`ty`/`tz` channels) → `null1` (a plain junction CHOP, referenced rather than the raw producer — same "reference a Null, not the producer" convention as the feedback-loop template) → the target `geo1`'s Instance-page pars: `instancing=1`, `instancecountmode=oplength`, `instanceop=<path to null1>`, `instancetx/ty/tz='tx'/'ty'/'tz'`. `geo1` needs its own `material` par set to a MAT (e.g. `phongMAT`) or the render is black regardless of instancing.
- **This particular TD install's Geometry COMP defaults to a POP-family internal network** (`torus1`, a `torusPOP`), not the classic SOP shown in the official example. Both families are valid render sources for a Geometry COMP (`POP` docs: "creates/modifies 3D data which is rendered by the Render TOP") — this is a per-install/version default, not a hard requirement. `POP to CHOP` (`poptoCHOP`, not `popToCHOP` — verify Python class names with `hasattr(td, name)` before guessing) needs its own attribute-scope config (`attribscope='P'`) and its channel naming (`P_0`/`P_1`/`P_2` with `nameformat=basic`) is **not** the same convention as `SOP to CHOP`'s `tx`/`ty`/`tz` — confirmed by reading back real channels via `/chop`, never assumed.
- **The single costliest gotcha**: a manually `/create`-d SOP/POP placed *inside* a Geometry COMP does **not** inherit `display=true`/`render=true` the way the COMP's own auto-generated default content does. A freshly created `geometryCOMP` ships with a `torus1` (or equivalent) that already has both Common Flags on; a hand-added `sphere1` via `/create` had **both flags `false`** by default, producing a completely black/all-zero render (`numpyArray` all zeros, confirmed numerically) with **zero errors or warnings anywhere** — `/errors` is silent because this isn't a cook failure, it's a node that cooks fine but is deliberately excluded from the render. `render1.par.render`, `geo1`'s own `render`/`display` flags, camera/light `near`/`far`/`dimmer` all checked out identical between a working and a broken setup — the actual differing state was one level deeper, on the *inner* template-shape node. When a Render TOP outputs all-zero pixels with a fully clean `/errors` scan, check every SOP/POP/COMP actually contributing to the visible chain for its own `display`/`render` Common Flags via `/flag`, not just the top-level Geometry COMP's.
- Verify "no errors" is insufficient for a render pipeline specifically — confirm with actual pixel data (`TOP.numpyArray()` min/max/mean via `/run`, or `/snapshot` + `view_image`), since a render can cook without exception and still produce nothing visible.

**Container/Panel COMP connections: containment and wiring both establish "panel parent," and wiring wins.** Unlike a TOP/CHOP/SOP chain — where only wires matter and network containment is irrelevant — a Panel COMP's (`containerCOMP`, `buttonCOMP`, etc.) effective parent for Panel Value inheritance can come from *either* source, per `PanelCOMP.panelParent()`'s own docs: "a panel parent is the panel wired to the input of this operator, **or if that does not exist**, the panel containing this operator." Verified live with a throwaway probe (`_containertest_root`, destroyed after): a `buttonCOMP` nested inside a `containerCOMP` with no wire got `panelParent() == <the containing container>` and an empty `inputCOMPs`; a sibling `buttonCOMP` created *outside* that container but wired to it via `child.inputCOMPConnectors[0].connect(sourcePanel)` got `panelParent() == <the wired source>` instead, with `inputCOMPs == [<the wired source>]` — the wire took precedence over physical containment entirely (the wired child wasn't even nested inside the source panel's network location). Practical implications:
- Nesting a panel inside a Container in the network tree is sufficient on its own to establish parent/child panel behavior (alignment, anchors, Match Network Nodes, etc.) — no wire is needed for the common "build a control panel out of nested containers" case.
- A wire is only needed when the panel you want as the *value parent* lives somewhere else in the network than where you want the child to physically sit — and if both exist (contained *and* wired to something else), the wire wins, which can silently override the container's own layout/alignment behavior for that child. If a nested panel isn't responding to its visual container's `align`/`justify`/anchor settings, check `panel.inputCOMPs` for a stray wire before assuming the Container-page pars are wrong.
- `COMP.inputCOMPs`/`outputCOMPs` (and their `*Connectors` counterparts) are the read-only way to inspect actual wired Panel COMP connections, independent of network containment — use these over guessing from `/network`'s `wires` list when debugging a container.

**`/layout` (COMP.layout(), the Shift+L equivalent) is the fix for both organizing a messy network and placing new nodes cleanly.** Verified live: three `nullTOP`s created at deliberately scattered/overlapping coordinates, wired `a → b → c`, snapped into a single non-overlapping horizontal line in wire order after one `POST /layout?paths=a,b,c&horizontal=true` call. This reframes node placement — don't try to hand-compute good `x`/`y` for new nodes (the existing `_auto_place` heuristic in `/create` is a local, one-node-at-a-time guess and doesn't understand branches/loops); instead, create/wire the chain wherever's convenient, then call `/layout` on just the newly created set to let TD's own layout engine arrange it in line with its connections and clear of overlap. See [.ai/skills/td-http-api.md](.ai/skills/td-http-api.md) for the route and the verification discipline that should follow every call.

## See Also

- [.ai/skills/td-http-api.md](.ai/skills/td-http-api.md) — the HTTP tooling every step here relies on (`/network`, `/dat`, `/snapshot`, `/chop`, `/diff`, `/create`, `/run`, template routes).
- [data/harness/network-templates/](data/harness/network-templates/) — where verified Tier-2 rebuilds are captured as reusable templates.
