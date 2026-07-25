---
name: td-http-api
description: HTTP bridge into a running TouchDesigner project via a Web Server DAT — read/write network structure, params, and DAT scripts, hot-reload Python modules, and create/wire nodes, all from outside TD. Use when an AI agent or external tool needs live access to TD project state.
---

# td_http_api

`python/util/td_http_api.py` is a self-contained Web Server DAT callback module that exposes a running TouchDesigner project over local HTTP. It's the bridge that lets an AI coding agent (or any external tool) inspect and modify a live `.toe` without going through the Textport or the UI.

## Mandatory Agent Checklist

- **Prioritize atomic routes over monolithic scripts.** Prefer `/create`, `/wire`, `/par`, `/move`, `/comment`, `/flag`, and `/annotate` over `/run`. Use `/run` only when the operation cannot be expressed through existing deterministic routes.
- **No stacking in multi-node builds.** Always provide explicit `x` and `y` for `/create` in planned multi-node layouts. Do not rely on auto-placement for chain readability; treat `_auto_place` as a fallback only for one-off nodes.
- **Viewer hygiene.** Ensure user-visible terminal/output nodes are viewable immediately (`viewer=true` at create time, or set viewer/display/render state explicitly via deterministic routes).
- **No shell heredocs for script payloads.** When `/run` is required, write a real file and send with `--data-binary @file` to avoid escaping/backslash corruption.
- **Resolve first, mutate second.** Confirm the active network root via `/network` (and `/selected` only as supporting signal) before any write call.

Companion utility: `python/util/td_util.py` holds general-purpose op helpers (node color/size, op-tree printing, current-network lookup) used from the Textport. `td_http_api.py` deliberately does **not** import it — the network-description logic (`describe_network`, `network_to_mermaid`, param serialization) is duplicated inline so this one file can be dropped into any project as a single Callbacks DAT with zero other dependencies.

---

## Setup

**Fastest path — drop in the packaged component:** `tox/haxlib/net/TdHttpApi.tox` is a self-contained, drop-in COMP wrapping the Web Server DAT + an embedded copy of the callback code, plus a `readMe` and file-synced copies of the skill docs. Drag it into any project (or `op('/project1').loadTox(...)`), and it starts serving on port 3031 automatically — no wiring needed. It has a `readMe` DAT inside with getting-started notes. (Two routes degrade in a non-haxlib project: `/reload` needs `op.App`, and the `docs_*` DATs point at `.ai/skills/*.md` — everything else is self-contained.)

**Manual setup** (or to keep the live-edit/hot-reload workflow in this project):
1. **Text DAT for the callback code** — create a Text DAT (e.g. `Td_http_api`), sync its file to `python/util/td_http_api.py`.
2. **Web Server DAT** — add one, set its **Callbacks DAT** parameter to the `Td_http_api` Text DAT, pick a **Port** (dev convention in this project: `3031`), turn **Active** on.
3. **Verify**: `curl http://127.0.0.1:3031/network` should return JSON.
    Note: Use `127.0.0.1` instead of `localhost` to avoid potential DNS/IPv6 resolution delays.

Note the packaged `.tox` embeds a *snapshot* of the callback code; the canonical source stays `python/util/td_http_api.py`. After meaningful changes to the routes, re-export the `.tox` (build a wrapper COMP, embed the current file text into its `callbacks` DAT, save) so the drop-in doesn't drift.

### Picking up code changes

Two different reload mechanisms are in play, and mixing them up is the most common source of "why isn't my change showing up":

| What changed | How it gets picked up |
|---|---|
| `td_http_api.py` itself | The Callbacks DAT's file-sync must refresh (usually automatic; if a brand-new route 404s right after editing, manually reload the Text DAT's file sync once) |
| Any other project Python module (`td_util.py`, `App.py`, etc.) | `GET /reload` — hits `op.App.ReloadModules()` → `config.ReloadModules()`, which walks `python/`, `python/util/`, `python/app/`, `python/net/` and `importlib.reload()`s anything already in `sys.modules` |

`/reload` itself reloads `td_http_api.py` too (it's a normal file-based module from `config.ReloadModules()`'s point of view, in addition to being Callback-DAT content) — so the usual loop when iterating is: edit the file → `curl .../reload` → retest.

---

## Best Practices

- **Minimize Request Volume.** Each HTTP request triggers a callback on TouchDesigner's main thread. For large-scale network modifications (e.g., creating dozens of nodes), avoid sending many individual `/create`, `/wire`, or `/par` requests. Instead, group your logic into a single Python script and use the `/dat` route to upload it, then execute it within TD.
- **Determinism-first: prefer an existing route over a `/run` script, and prefer a real route over a repeatable `/run` script.** Before writing any `/run` script, check two things in order: (1) does a route already cover this? (2) is the thing being set actually a `Par` (`/par` works) or a bare OP/COMP attribute like a "Common Flag" (`bypass`, `render`, `display`, `lock`, `viewer`, `selected`, `current`, `allowCooking`, `cloneImmune`, `expose`, `python`, `showCustomOnly`, `showDocked`, `activeViewer` — see `/flag` below)? If a one-off `/run` script's pattern looks likely to recur, promote it into a real route in `td_http_api.py` instead of leaving it as throwaway Python — that's exactly how `/flag` came to exist (generalized from a one-off `/bypass` hack). Ask "could this become a route?" before reaching for `/run`. This keeps the system's capabilities discoverable and reusable across sessions instead of re-deriving the same Python each time.

---

## Operating the API as an agent (client-side notes)

Hard-won workflow lessons for an agent *using* this API (as opposed to the server-side behavior documented elsewhere):

- **Author `/run` scripts with the Write tool, then `curl --data-binary @file`. Do NOT build them with shell heredocs.** A `<<'EOF'` heredoc mangled backslashes twice this project (`.replace('\\', '/')` arrived as `.replace('\', '/')` → SyntaxError). Every temporary `/run` script and captured response must be created under the project-local `tmp/` directory — never in the project root, `python/`, `scripts/`, or another source directory. Use a distinctive filename such as `tmp/td_run_inspect_<purpose>.py`, POST it with `--data-binary @d:/workspace/haxlib/tmp/td_run_inspect_<purpose>.py`, and delete it after verification. Before finishing, check that no temporary `.py` probe remains outside `tmp/`. Avoid backslashes in the script entirely — `project.folder` is already forward-slash (`D:/workspace/haxlib`), so build paths with `/`.
- **Parse `/run` responses as `{output, [error]}`.** Pipe through `python -c` to print `output` and surface `error`. A missing `error` key means success.
- **In PowerShell, always call `curl.exe`, never `curl`.** PowerShell aliases `curl` to `Invoke-WebRequest`, which returns a rich object rather than raw text. Piping that into Python (`json.load(sys.stdin)`) produces empty input and a `JSONDecodeError`. Add `.exe` explicitly on every curl call in PowerShell sessions.
- **Annotation nodes (`annotateCOMP`) are utility nodes — `op(path)` returns `None` for them.** They don't appear in `parent.children` and can't be resolved with a bare `op('/some/path/comment7')` call. In `/run` scripts, access them via `parent.findChildren(name='comment7', depth=1, includeUtility=True)[0]`. The `/par` and `/network` routes handle this transparently via `_resolve_op`'s utility-node fallback, but raw Python inside `/run` does not.
- **Don't pass multiline or special-character values as PowerShell variables into `curl.exe` query params.** PowerShell truncates or mangles long `%`-encoded strings during variable interpolation. Instead, put the mutation in a `/run` script file and POST with `--data-binary @file`. This is the correct pattern for any body text that contains newlines, quotes, or non-ASCII.
- **A `\uFFFD`/mojibake in curl output is usually a display artifact, not data corruption.** Non-ASCII (em-dashes, `Δ`, etc.) round-trips fine through TD and `.tox` storage but can render garbled through the curl→python→Windows-console pipe. Before "fixing" a suspected encoding bug, confirm in-process (e.g. `sum(1 for ch in dat.text if ord(ch) > 127)`) — the stored data is usually clean. (That said, ASCII-only is still the safe choice for user-facing text like a `readMe`.)
- **Never reconfigure or reparent the Web Server DAT you're currently talking through.** Modifying the live server risks cutting your own connection mid-operation. To build/modify server infrastructure, create a *fresh* component, test it on an alternate port (e.g. 3032/3033), verify, then save/swap — leaving the live server untouched until the new one is proven.
- **Probe hygiene.** Temp COMPs created for inspection/testing should use a distinctive `_`-prefix (`_snippet_probe`, `_verify`, …), be destroyed at the end of the same script that made them, and their destruction verified (`op(path) is None`). Re-run recon after multi-step builds to confirm nothing leaked.

### Resolving the user's current network

Before any user-requested mutation, establish the network currently shown in the TouchDesigner Network Editor. Do not infer it from the previous task, the currently open source file, a similarly named component, or an empty selection.

Use this order:

1. Call `GET /network` without a `path`; its `root` identifies the Network Editor's current COMP and its `nodes` provide the read-only context.
2. Call `GET /selected` as supporting evidence only. An empty selection does **not** identify the current network, and a selected child does not necessarily mean it is the requested target.
3. If the default `/network` response fails or cannot be parsed, use a read-only `/run` probe to print the active Network Editor owner path:

   ```python
   pane = ui.panes.current
   if pane is None or pane.type.name != 'NETWORKEDITOR':
     pane = next((p for p in ui.panes if p.type.name == 'NETWORKEDITOR'), None)
   print(pane.owner.path if pane is not None else '/')
   ```

4. Re-query `/network?path=<resolved owner>&recursive=false` only after the owner path is known. If that path-specific request fails, report the API error and ask the user to identify the network; do not substitute a similarly named component.

Record the resolved path in the plan and use it explicitly as `parent` for every write request. If the user says "this Base COMP" but the resolved owner is a child network or a different component, pause and clarify before modifying anything. Resolve first, inspect second, mutate last.

### Organizing scattered experiment networks

When asked to clean up a network containing scattered experiments, use this workflow:

1. Query the current network with `GET /network?path=<current>&recursive=false`. Work from direct children only when the request is to organize the current network.
2. Inspect the response's `wires` and `references` before moving anything. Infer experiment groups from actual connections, referenced helper DATs/CHOPs/MATs, script contents, and clear names; do not group by proximity alone.
3. Preserve every node's parent. In particular, never move nodes into a `baseCOMP` or another child network just to make the layout look organized. A `networkbox` annotation provides visual grouping without reparenting its enclosed nodes.
4. Use absolute `/move` requests (`path`, `x`, `y`) when nodes are scattered. Relative group moves are appropriate only when the group's existing internal arrangement is already useful. Choose stable grid columns and row bands, keep connected chains left-to-right, and leave space between experiment bands for annotations.
5. Create one `networkbox` annotation per coherent experiment with `POST /annotate`, passing its comma-separated `paths`, descriptive `title`, unchanged `parent`, and a modest `pad`. Useful labels describe responsibility, such as `Feedback studies`, `POP geometry`, or `Ramp scripting`.
6. Validate after moving and annotating: re-query the network, confirm all original nodes still have the intended parent and coordinates, check each annotation's `enclosedOPs`, and verify its visible title through `customPars.titletext.value`.

Keep ambiguous nodes separate rather than inventing a relationship. Existing experiment COMPs generally deserve their own grid cell or clearly labeled group; a connected chain and its referenced helpers belong together; a script DAT may join a group only when its contents clearly identify that subsystem.

#### Deterministic rules for smaller models

Treat network organization as a finite two-pass operation, not an open-ended layout search. Before making changes, record these invariants:

- The current network is the only allowed parent.
- No node may be moved into a `baseCOMP` or any other child network.
- Existing wires and parameter references must remain unchanged.
- The final set of original node paths must equal the initial set; only annotation nodes may be added.

First produce a group manifest before issuing any move requests. Each group should list its node paths, the evidence for the grouping, its grid column/row, and the left-to-right order within the group. Use evidence in this order: direct wires, OP parameter references, DAT contents, existing experiment COMP names, naming similarity, and spatial proximity only as a last resort. If the evidence is ambiguous, mark the node unclassified and leave it separate instead of repeatedly reconsidering it.

Use fixed layout constants rather than inventing coordinates node by node. For example, choose a column spacing, row spacing, within-group node spacing, and annotation padding, then derive absolute `x`/`y` positions from the manifest. Keep connected chains left-to-right and reserve enough empty space around each row for its annotation.

Execute in this exact order:

```text
inspect -> classify -> move -> validate -> annotate -> validate
```

After the move pass, compare the original and current direct-child path sets, confirm every node's parent, and verify the expected coordinates. Only then create annotations. After the annotation pass, verify the annotation count, each `enclosedOPs` set, and each visible `customPars.titletext.value`. Do not keep optimizing once these checks pass.

### Re-exporting the drop-in `.tox`

To rebuild `tox/haxlib/net/TdHttpApi.tox` after meaningful route changes (via `/run`):

1. Create a wrapper `baseCOMP` (temp location, e.g. `/project1/TdHttpApi`).
2. Create a `callbacks` `textDAT`; embed the current source: `callbacks.text = open(project.folder + '/python/util/td_http_api.py').read()`; set `language='python'`.
3. Create a `webserver` `webserverDAT`; **delete the auto-spawned `webserver_callbacks` stub** it creates; set `par.callbacks = callbacks`, `par.port = 3031`, `par.active = True`.
4. Add the `readMe` (ASCII) and the `docs_*` DATs (`par.file` → the `.ai/skills/*.md` paths, `syncfile` on).
5. Test on an alternate port first (`par.port = 3032`) → `curl` a couple routes → then reset to 3031.
6. `comp.save(project.folder + '/tox/haxlib/net/TdHttpApi.tox')`.
7. **Round-trip verify**: `loadTox` the saved file into a throwaway COMP on a spare port, curl it, then destroy the probe.
8. Destroy the build instance so the project keeps only its original live server.

---

## Invoking an agent from the shell

For a quick one-shot fix (rather than an interactive session), the `pi` CLI can run a single LLM session against a locally-hosted model directly from the shell. Verified working prompt for "there's an error in whatever network I'm currently looking at, go fix it":

```bash
pi -p "Can you use the td-docs-mcp mcp server and the td_http_api.py tools, along with the td-http-api.md skill to solve the error in the network that I'm currently looking at in the touchdesigner UI?"
```

### From TD's own Textport — `python/util/harness_util.py`

Same command works from inside TD's Python console too, via `subprocess` — but run it threaded (per [.ai/skills/td-threading.md](.ai/skills/td-threading.md)'s Subprocess Pattern), since the Textport executes synchronously on the main thread and a blocking call would freeze the whole TD UI for however long the LLM session takes. That threading wrapper now lives in `python/util/harness_util.py`:

- **`run_pi_agent(prompt: str)`** — the generic, non-blocking runner. Launches `pi -p <prompt>` in a background thread, streams its output to the Textport line-by-line as it arrives, returns immediately.
- **`PROMPTS`** — a dict of named, reusable prompts, so call sites reference a name instead of duplicating a prompt string. Currently has `'fix_network_errors'` (the prompt above). Add new entries here as new use cases come up — this is meant to grow into a small library, not stay a one-off.
- **`run_named_prompt(name: str)`** — looks up `PROMPTS[name]` and runs it via `run_pi_agent`. Raises `ValueError` (listing available names) on an unknown name.

`App.py` exposes this globally as **`op.App.FixNetworkErrors()`** — a thin wrapper calling `harness_util.run_named_prompt('fix_network_errors')`. Callable from anywhere via the global `op` reference, not just the Textport (a Panel button's callback, a keyboard shortcut, another extension, etc.).

```python
# from anywhere with TD op access:
op.App.FixNetworkErrors()

# or directly, for a prompt not yet wrapped in App.py:
import harness_util
harness_util.run_named_prompt('fix_network_errors')
harness_util.run_pi_agent("some one-off prompt not in the library")
```

Note: `App.py` is a TD extension file, excluded from `config.ReloadModules()`'s walk — picking up an edit to `App.py` itself depends on TD's own extension-file-sync-on-save, not `/reload`. `harness_util.py` is a normal file-based module, so `/reload` (or `td.reloadModules()`) does pick up changes to it.

This names all three pieces the agent needs: `td-docs-mcp` (TD operator/Python API documentation lookup), `td_http_api.py`'s HTTP routes (`/errors` to find it, `/par` to read/fix it, per the error-troubleshooting workflow above), and this skill doc itself for the concepts/gotchas. Matches the exact workflow that found and fixed a real `SyntaxError`+`NameError` pair in `/project1/InstagramPreview/level1.opacity` end to end with no manual TD UI interaction.

---

## Concepts

**Two separate module systems.** TD's Callbacks DAT dispatch (how `onHTTPRequest` gets invoked) is independent of Python's `sys.modules` import cache. A Text DAT synced to a file re-executes its own content when the file changes; `import some_module` elsewhere in the project is cached separately and needs `importlib.reload()`. This is why the table above has two different rows — they're genuinely different mechanisms, not two names for the same thing.

**Everything here mutates live state.** `/par`, `/dat` (POST), `/create`, and `/wire` write directly into the running project — no confirmation dialog, no guaranteed undo-stack entry the way a UI edit gets. Treat this server as trusted-caller-only: keep the Web Server DAT's port off any network interface reachable by anyone other than you, since there's no auth on these routes.

**References vs wires.** `describe_network()` distinguishes TD's two link types: solid-line **wires** (`OP.inputs`) versus dashed-line **references** (`Reference`/`Link` in TD's own docs) — OP-type params, parameter binds, CHOP exports, and `op()`/`opex()` calls found inside expression-mode param strings. Only *non-default* param values are considered for references and for the `customPars` block on each node — this mirrors the params dialog's "Show Custom Only" toggle and keeps default-valued boilerplate (`dragscript`, `opviewer`, etc.) out of the output.

**Check the unit before setting a transform/position parameter.** Many TOP/CHOP spatial params (Transform TOP's `tx`/`ty`, etc.) have a companion unit parameter (e.g. `tunit`) that's commonly `fraction` — normalized to the image's own size, where `1.0` means "shift by one full width/height," not one pixel. Before driving a value via `/par`, read the unit param first (`GET /par?path=...&par=tunit`) rather than assuming pixels — an amplitude/offset that looks reasonable as a raw number can be an order of magnitude too large (or small) if you guess the unit wrong. First-hand example: an LFO CHOP driving `transform1.tx` was set to amplitude `150` assuming pixel-ish scale; `tunit` was actually `fraction`, so `150` meant "150 image-widths of travel" — corrected down to `0.1` (±10% of width) after checking.

**`/create` defaults to the currently-open network and auto-places new nodes — but still verify.** Omitting `parent` targets whatever network is open in the TD UI (via the same lookup `/network` uses), not project root — this was added specifically because an agent once guessed wrong and put nodes in root. Omitting both `x` and `y` triggers auto-placement: the new node is positioned to the right of its `inputs` (or right of existing siblings if there are none), nudged down to clear any overlap. This gets you a reasonable *default* layout automatically, but it's still a heuristic, not real graph layout — for a multi-node build, it's worth calling `/network` afterward to sanity-check the result rather than assuming it came out clean, especially once the chain branches or loops back on itself (e.g. a feedback loop).

**`/layout` (Shift+L) fixes messy placement after the fact — but scope it tightly and always re-check, or it makes its own mess.** `COMP.layout(ops, horizontal=/vertical=/gridRows=)` snaps the given ops into a clean, non-overlapping line/grid in wire order — verified live on a deliberately scattered 3-node chain, which came back in a straight line in connection order after one call. It's the right tool for "these new nodes ended up far from what they connect to" (point 2 above) and for general network tidy-up (the same job as the "Organizing scattered experiment networks" workflow), but it has its own failure modes an agent needs to guard against:
- **Scope `paths` to exactly the nodes you mean to move.** Omitting `paths` lays out *every* direct child of `parent` — including nodes the user hand-placed deliberately, any existing annotation-enclosed groups, and anything outside the chain you were actually fixing. Prefer an explicit `paths` list (the newly created/wired set, or a `/bounds`-derived set of "obviously scattered" nodes) over the no-`paths` whole-network form unless the user asked to tidy up the entire network.
- **`/layout` doesn't know about `annotateCOMP` boxes.** A `networkbox` annotation's `enclosedOPs` is computed from node positions at creation time (per `/bounds`); moving the enclosed nodes via `/layout` without also re-deriving/re-creating the annotation can leave a stale box that no longer actually encloses its nodes. Re-check (or recreate) any annotation whose contents you just laid out.
- **Always verify after calling it, the same way as after a manual multi-node build**: re-`/network` (or use the `nodes[]` this route already returns) to confirm the moved set doesn't now overlap *other* siblings that weren't part of the call, and that nothing outside the intended `paths` shifted. Treat `/layout`'s own response as a first-pass check, not a substitute for the same "did this actually come out clean" scrutiny `/create`'s auto-placement already gets above — an automated layout tool having *a* rule to follow doesn't mean its result is automatically correct for this specific network.

**`/save` and `/save-external-tox` solve different problems — don't reach for the wrong one.** `/save` is `project.save()`: the whole `.toe`, same as Ctrl+S. It leaves referenced `.tox` files alone unless `saveExternalToxs=true` is passed, and even then it cascades across *every* external-tox-backed COMP in the project. `/save-external-tox` is narrower and was added specifically for the td-http-api authoring workflow: it targets one named COMP and calls `COMP.saveExternalTox()` on it directly, writing that COMP's current contents to its already-configured `externaltox` path — independent of whether TD's own dirty-tracking flagged it, and independent of a project save. This matters because a COMP's external `.tox` doesn't always get re-exported just because something it depends on changed (verified live: editing `td_http_api.py` — file-synced into `TdHttpApi/callbacks` — and calling `/save` afterward left `tox/haxlib/net/TdHttpApi.tox` completely untouched on disk, same mtime and byte size; the COMP wrapping the callbacks DAT apparently wasn't considered dirty by that edit path). So after a route change meant to ship in the packaged drop-in `.tox`, save the project if you like, but use `/save-external-tox?path=/project1/TdHttpApi` to actually get the updated `.tox` written — that's the one that reflects reality here, not `/save`.

**Give forked-and-rejoined branches their own horizontal lane, don't stack them under the fork/rejoin points.** When a node's output forks into a side-branch that later reconverges downstream (the canonical case: a Feedback TOP loop, where a junction node feeds both the main composite directly *and* a feedback/decay branch that rejoins the same composite's second input), the readable layout widens the gap between the fork node and the rejoin node so the entire side-branch's nodes fit horizontally *between* them — each on its own column — rather than placing branch nodes directly above/below the fork or rejoin node's column. Concretely, from the feedback-loop template: `null1` (fork) and `comp1` (rejoin) got pushed apart by however many columns `feedback1`+`level1` needed, and those two sit in that gap on their own row, not stacked under `null1`/`comp1`. Keep the branch row's vertical offset modest, too — around half the offset of a full separate row (e.g. 100 units, not 200) reads as "related to and feeding back into the main row" rather than "a disconnected second structure." This is a manual layout convention for now, not something `_auto_place` does automatically — see Roadmap.

**`/snapshot` closes the one blind spot every other route leaves open: actually seeing pixels.** Everything else in this API is structural or numeric — node types, wiring, parameter values, error text. None of it tells you what a TOP's output actually *looks* like. `/snapshot` uses `TOP.saveByteArray()` to render the current frame to an in-memory PNG (or `.jpg`/`.bmp`/`.tif`/`.exr`/`.dds`, no disk write needed) and returns it directly as the HTTP response body — `curl -o file.png ".../snapshot?path=..."` then read the file as an image. Verified live: fetched a snapshot of a Composite TOP mid-feedback-loop and could see the actual rotated video frame with composite fill, the first real visual confirmation in an entire session that had otherwise been pure numbers. Defaults to `force=true` (force-cooks before capturing) for the same reason `/errors` does — a TOP nothing is viewing may not have cooked recently, so the snapshot could otherwise be stale.

**`/duplicate` doesn't retarget references pointing outside the copied set.** `COMP.copy()`/`copyOPs()` preserve *wires* between duplicated nodes automatically, but a duplicated node's parameter *references* (a Feedback TOP's `top`, a bind, an expression) still point at whatever the original referenced — even if that thing was also duplicated in the same call but under a different role. Verified case: duplicating `feedback1`+`level1` together preserved the `feedback1→level1` wire in the copies, but the copy's `top` param still pointed at the original `comp1`, not a copy of it (since `comp1` itself wasn't part of the copied set). If you need a fully independent duplicate of a loop, the rejoin/target node has to be in the copied set too, and its `ref`-style params re-pointed by hand afterward via `/par`.

**`/errors` does catch broken parameter expressions — real Python `SyntaxError`/`NameError` text comes through verbatim.** Confirmed live: a Level TOP's `opacity` set to `sin(absTime.seconds)+1)/2` (unmatched `)`) surfaced as `Error: SyntaxError: unmatched ')' (, line 1) Context:(Parameter: Opacity)` after a forced cook, and fixing the parens but leaving bare `sin` (TD's expression namespace doesn't auto-import `math` functions — use `math.sin`, not `sin`) surfaced a follow-up `NameError: name 'sin' is not defined`. Both were fixed and confirmed clean via a second `/errors?paths=...` call. So: `/errors` **is** the right first stop for "this node isn't behaving right, why" — including for expressions, not just file/shader/target-reference failures.

Earlier testing on a *different* node/expression pair (a Transform TOP's `tx`/`rotate`, with `op('does_not_exist').par.value0` and a bare unclosed `math.sin(`) failed to surface anything even after a forced cook — that discrepancy is unresolved. A plausible guess: an unclosed call like `math.sin(` is ambiguous to Python's parser (`unexpected EOF while parsing` — could look like "still being typed") versus an unmatched extra `)` , which is unambiguously broken, and TD may suppress the former differently than the latter. Not confirmed — if `/errors` ever comes back clean on something you're sure is broken, don't fully trust that "clean" without also reading the parameter back directly (`GET /par?path=...&par=...`) to sanity-check its `expr`/evaluated `value`.

**`OP.bypass` (and a whole family of similar OP booleans) is a Python attribute, not a parameter — `/par?par=bypass` 404s with "no parameter named 'bypass'".** TD's own docs group these under OP's "Common Flags": `activeViewer`, `allowCooking`, `bypass`, `cloneImmune`, `current`, `display`, `expose`, `lock`, `python`, `render`, `selected`, `showCustomOnly`, `showDocked`, `viewer` — none of them are `Par` objects, so `/par` (which only reads/writes `Par`s) can never reach any of them. **This is now a deterministic route, not a one-off script**: `POST /flag?name=<flag>&value=<bool>&path=...` (with the same `path`/`paths`/`family`/`recursive` targeting as `/errors`) covers the whole family; `/bypass` is a thin alias for `name=bypass`. Prefer `/flag` over a fresh `/run` script for any of these 14 flags — that's exactly the kind of one-off Python this route exists to eliminate. If a future need turns up a *new* non-`Par` OP attribute outside this list (e.g. `cook()`, `destroy()`), that's still `/run` territory unless/until it's common enough to deserve its own deterministic route too.

**`path` alone means "this exact node," not "scan this COMP's children."** On `/flag` (and `/errors`), a bare `path` with no `family`/`recursive` is treated as a single explicit target. To bypass every TOP *inside* a COMP, pass `family=TOP` (and/or `recursive=true`) — passing just the COMP's own path will instead try to set the flag on the COMP itself.

**A blank/all-black Render TOP with a fully clean `/errors` scan is very often a `display`/`render` Common Flag left off on some node deep in the render chain, not a wiring or material problem.** Confirmed live (see the instancing craft note in [.ai/skills/td-network-craft.md](.ai/skills/td-network-craft.md)): a Geometry COMP's own `render`/`display` flags, its `material` par, the Render TOP's `camera`/`geometry`/`lights` refs, and the camera/light's `near`/`far`/`dimmer` were all identical between a working and a completely blank setup — the actual difference was one level deeper, on a manually `/create`-d SOP *inside* the Geometry COMP, whose own `display`/`render` flags defaulted to `false` (a COMP's auto-generated default content, e.g. a fresh `geometryCOMP`'s built-in `torus1`, already has both on — a hand-added replacement shape does not inherit that). `/errors` stays silent because the node cooks fine; it's just excluded from the render, on purpose as far as TD is concerned. Verify a "why is nothing rendering" mystery with actual pixel data — `TOP.numpyArray().mean()` via `/run`, not just an eyeballed `/snapshot` PNG (a fully transparent all-zero RGBA render can look identical to a valid white background in an image viewer) — then check `/flag`'s `display`/`render` on every contributing node, innermost first.

**This project's `TdHttpApi` Callbacks DAT has `syncfile=true` pointed at `python/util/td_http_api.py` — edit the file, don't `POST /dat` the route code.** It's easy to assume (wrongly) that a packaged/embedded server has no file-sync and needs its live DAT text pushed directly via `/dat`. Check first (`GET /network` on the COMP holding the Web Server DAT shows each Text DAT's `customPars.file`/`syncfile`) — if `syncfile` is on, plain-old file-sync already picks up an on-disk edit with no extra step. Pushing route-code changes through `/dat` on a file-synced DAT risks a sync-back interaction that can corrupt the on-disk file (observed live: the on-disk `td_http_api.py` was overwritten with the literal `repr()` text of its own bytes — `b'import io\r\nimport json...'` as one giant one-line string — immediately after such a push, breaking every route including `/run` itself with no HTTP-only way back in). If that ever happens again: check `git status`/`git diff --stat` on the file first — a clean git history is the fastest recovery (`git checkout -- <file>`), faster than trying to hand-repair a corrupted multi-thousand-character single line.

**When a `/run` edit is genuinely one-shot, write the script once and do it right the first time — don't probe-then-fix.** The `bypass` investigation above took an avoidable detour: first attempt used `/par` (wrong route), then a probe script to check `hasattr`, *then* the actual mutation script — three round trips for a one-line change. Once it's established that a route needs `/run` for a batch of paths, compose the complete script (loop + mutation + JSON result print) in a single `create_file`/`replace_string_in_file` pass, curl it once, and delete it — same discipline as the "Minimize Request Volume" best practice above, just applied to script *authoring*, not just HTTP call count. A short list of known non-`Par` OP attributes reachable only via `/run`: `bypass`, `cook` (force-cook), `destroy`, `.par` iteration itself (`o.pars()`), `selected`/`current` (UI state, not OP state).

**`/errors` results reflect whatever TD last cooked, not the current parameter state, unless force-cooked.** A node that isn't being viewed or pulled on by anything may simply never re-cook after you change it, so `.errors()`/`.warnings()` can read clean on a genuinely broken node just because TD hasn't tried yet. This is why explicit `paths` targets default to `force=true` (cook it now, then check) while a broad `path`/scan defaults to `force=false` (checking a whole network's cook state as-is, without forcing every node in it to cook just to look).

**`/diff` will show noise from any live/animated parameter, and that's expected, not a bug.** A param driven by an expression referencing an oscillating CHOP (e.g. an LFO) will almost always show a different evaluated `value` between a "before" and "after" snapshot, even with zero structural change — the expression and mode stay identical, only the momentary evaluated number differs. Read a `changed` entry's `expr`/`mode` before concluding the param was actually edited; if those match and only `value` differs, that's just the animation ticking, not something the diffed operation did. Also worth knowing: `/tmp` was unreliable in at least one Windows/Git-Bash environment used to build this tool (writes silently hung); the project's actual scratchpad directory worked fine — if snapshot files being written for a `/diff` call mysteriously hang, that's the first thing to check, not the server.

**`/annotate` is the tool for the "group nodes by responsibility, document as you go" workflow.** `Titletext`/`Mode`/`encloseops`/`Bodytext` are genuine built-in `annotateCOMP` parameters (confirmed against TD's own docs, not dependent on any per-project clone/extension setup) — a plain `parent.create('annotateCOMP')` has them directly. `mode='networkbox'` is the lean choice for visual grouping/labeling (spacing sub-networks apart, grouping by responsibility); `mode='annotate'` adds the full title+body+viewer feature set, better suited for actual prose documentation aimed at other developers. Verified live: enclosing `feedback1`+`level1` via `/bounds`' box-computation immediately populated the new annotation's `enclosedOPs` correctly — no extra cook/frame-tick needed.

#### What the user means by "annotation box"

When a user asks for an annotation box around nodes, interpret that as a TouchDesigner **`annotateCOMP` in `networkbox` mode** — a visual backdrop that encloses and labels existing nodes in the current network. It is not a `baseCOMP`, container, subnet, or reparenting operation. The enclosed operators remain where they are and keep their original parent; the box provides organization on the network canvas and can move with its enclosed operators.

Do not substitute these other objects:

- `baseCOMP`: a child network/container. Never use it for visual organization unless the user explicitly asks to restructure the network.
- `annotateCOMP` with `mode='comment'`: a floating post-it style note, not a group boundary.
- `annotateCOMP` with `mode='annotate'`: a richer documentation annotation; use it when the user wants substantial title/body/viewer content rather than a simple group box.

For a visual group box, use the current network as `parent` and pass the exact direct-child node paths in `paths`:

```text
POST /annotate
  parent=<current network>
  paths=<comma-separated node paths>
  mode=networkbox
  title=<short responsibility label>
  pad=40..60
```

The request creates one `annotateCOMP` beside the nodes; it does not move them into a subnetwork. Use one box per coherent experiment, not one box around the entire network. After creation, verify that the returned node has `opType=annotateCOMP`, `customPars.mode.value=networkbox`, the expected `customPars.titletext.value`, and the intended paths in `enclosedOPs`. If `enclosedOPs` is empty or incomplete, check the node coordinates, parent, and paths before creating another box.

### Standardizing Comments & Annotation Scales

To ensure clarity, documentation inside TouchDesigner networks operates across three distinct tools, designs, and workflows:

| Scale | Tool / Mode | TouchDesigner Equiv. | Purpose & Operational Use Case | API Route |
| :--- | :--- | :--- | :--- | :--- |
| **1. Node Comment** | Native Operator Comment (`OP.comment`) | Tucked-away Metadata | **Detailing localized single-node behavior.** Used for documenting specific parameter values, intricate Python expressions (e.g., opacity formulas), or code variables inside nodes. Has no visible outline, only a small flag on the OP tile. | `/comment?path=...&text=...` |
| **2. Comment Box** | `annotateCOMP` with `mode='comment'` | **Post-it Box** (Shift+C) | **General visual notes.** Sized flat boxes showing styled text floating in the network layer. Unlike raw metadata, they are highly readable on the canvas, but they don't enclose or structurally drag neighboring nodes with them. | `/annotate?paths=...&mode=comment&body=...` |
| **3. Annotation / Network Box** | `annotateCOMP` with `mode='networkbox'` or `'annotate'` | **Subsystem Wrapper** (Shift+A / Shift+B) | **Cohesive module packaging.** Sized backdrops enclosing direct children coordinates with `encloseops=True`. Moving the box translates all enclosed elements cleanly. Also allows other operators and scripts to query bound limits or enclosing borders. | `/annotate?paths=...&mode=networkbox` (or `mode=annotate`) |

By separating these three documentation options, we prevent layout dragging issues while providing highly readable layout guides across all scales.

#### The "Utility Node" path resolution gotcha (Crucial API Concept)
Both TouchDesigner comments (`Shift+C`) and annotation wrappers (`Shift+A`, `Shift+B`) are classified as "Utility Nodes" in TD. By default, when `utility=True` is set on them:
* Direct python references like `op('/path/to/utility1')` evaluate immediately to `None`, making utility nodes invisible to standard paths.
* To safely locate, read, or dynamically delete utility nodes via external HTTP calls, search methods must bypass default filters. Instead of using `.ops('*')` or `.findChildren(includeUtility=False)`, the API must call **`.children`** or specify **`includeUtility=True`** inside findChildren calls:
  `parent.findChildren(name=name, depth=1, includeUtility=True)`
* Because of this architecture, our API has been hardened to recursively resolve utility nodes by parsing parental subdirectories when standard direct resolving fails. Always leverage this resolution pipeline to query backdrop metrics accurately!

**`/logs` exists to prove where time is actually being spent, not just to record activity.** Every request logs `callbackElapsedMs` — how long the Python side of `onHTTPRequest` itself took — separately from whatever the calling HTTP client measures end-to-end. This distinction is what actually nailed the POST-body-hang bug below: two `/create` calls with identical logic both logged `callbackElapsedMs` around 1ms, but the one missing a `Content-Length` header (visible in that entry's `requestKeys`) took 60s end-to-end anyway — proving the delay was entirely in POCO's HTTP layer, before `onHTTPRequest` ever ran, not anywhere in this file's Python code. When something is "slow," check `/logs` first to see whether the callback itself was actually slow, or whether (as here) it wasn't the callback at all.

**`inspect.getsource()` doesn't work reliably on handlers loaded from a Callbacks DAT.** `/routes` originally tried to classify each route's HTTP method by reading the handler's source text (looking for `_require_write_method`) — every single write route came back misclassified as GET-only. TD's DAT-based module execution doesn't give `inspect` a normal readable-file backing, even though this project's Callbacks DAT is genuinely file-synced. The fix was bytecode introspection instead of source text: `fn.__code__.co_names` (which names does this function reference — reliably present regardless of how the code was loaded) and `fn.__code__.co_consts` (literal constants embedded in it, useful for spotting an inline `request['method'] in ('POST', 'PUT')` check instead of the shared helper). One further gotcha within that: a tuple literal like `('POST', 'PUT')` usually gets folded into a single tuple object in `co_consts`, not exposed as bare top-level string constants — checking `'POST' in fn.__code__.co_consts` looks only at the top level and silently misses it; the tuple's contents have to be flattened first. A route that simply delegates to another route's handler (`/bypass` calling `_route_flag`) has no write-gate of its own to find either way, so this needed one level of recursion into any other `_route_*` name referenced in `co_names`, guarded by a visited-set against cycles.

---

## Routes

Routes are grouped by purpose. All responses set an appropriate `content-type`. Errors use `400` (bad input), `404` (unknown route), `405` (wrong method), or `500` (unexpected), always with a plain-text body.

### Read / Inspect

| Route | Method | Key params | Returns |
|---|---|---|---|
| `/network` | GET | `path` (default: open network), `recursive` (bool) | `{root, nodes[], wires[], references[]}` — each node includes position, size, `comment`, `customPars`, and `enclosedOPs` for `annotateCOMP` nodes |
| `/network.mmd` | GET | same as `/network` | Mermaid `flowchart TD` — paste into a ` ```mermaid ` block to render |
| `/selected` | GET | `path` (optional COMP) | Node summaries for `COMP.selectedChildren` — whatever is highlighted in the TD UI |
| `/dat` | GET | `path` | DAT's `text` (or `csv` for a table DAT) |
| `/par` | GET | `path`, `par` | `{name, mode, value, [expr]}` for that parameter |
| `/chop` | GET | `path` (CHOP), `samples` (default 100), `force` (bool) | `{numChans, numSamples, rate, channels: {chanName: [values…]}}` |
| `/snapshot` | GET | `path` (TOP), `format` (default `.png`), `quality`, `force` | Raw image bytes via `TOP.saveByteArray()` — no disk write. Use `curl -o file.png` to capture. |
| `/bounds` | GET | `paths` (explicit set) or `path` (COMP, bounds its children) | `{minX, minY, maxX, maxY, width, height, count, nodes[]}` |
| `/errors` | GET | `paths` (explicit, always force-cooks) or `path`/`recursive` (scan, `force=false` by default) | `[{path, opType, errors, warnings}]` — filtered to errored nodes unless `all=true` |
| `/health` | GET | `nodes` (optional comma-separated paths) | `{cookRate, realTime, webServerCpuCookTime, webServerTotalCooks, nodes[…]}` |
| `/server-info` | GET | — | `{webserver, port, active, callbacksDAT, callbacksFile, callbacksSyncFile}` — identifies the running bridge itself: is the Callbacks DAT file-synced (edit the file directly) or an embedded snapshot (needs `/dat` pushes)? Check this before deploying route-code changes. |
| `/docs` | GET | `name` (optional, hyphen/underscore-insensitive, works with or without the `docs_` prefix), `list` (bool) | Full text of the skill docs embedded alongside this server as sibling `docs_*` Text DATs (per the packaged `TdHttpApi.tox`) — no filesystem access needed. No params returns both docs with an onboarding preamble; `list=true` returns just `{docs: [...]}`. **This is the one-shot cold-start URL**: point a brand-new agent at `GET /` (aliased to this) or `GET /docs` and it has everything needed to start operating the bridge, no prior context required. |
| `/examples` | GET | `name` (optional DAT name, default `table_td_examples`), `q` (optional substring filter), `offset` (default 0), `limit` (default 50, max 500) | Queryable example database embedded inside the same `TdHttpApi` COMP as a DAT (default `table_td_examples`) so tox-only deployments can still serve curated examples without any external files. Returns `{source, columns, total, offset, limit, returned, rows[]}`. |
| `/examples.tsv` | GET | `name` (optional DAT name, default `table_td_examples`), `q` (optional substring filter) | Self-contained TSV export of the embedded examples database (`text/tab-separated-values`). Use this to regenerate `data/harness/op-snippets/catalog.tsv` directly from the running bridge with no helper script. |
| `/examples-refresh` | POST/PUT | `name` (optional DAT name, default `table_td_examples`), `q` (optional filter), `output` (optional file path, default `<project.folder>/data/harness/op-snippets/catalog.tsv`) | Writes the embedded examples catalog to disk from inside `td_http_api` itself. Deterministic replacement for external refresh scripts. Returns `{output, rows, columns, source}`. |
| `/routes` | GET | — | `[{uri, methods, summary}]` for every currently-registered route — generated live from `_ROUTES` and each handler's actual bytecode/docstring, so it always matches the running server exactly (unlike this prose table, which documents intent and can drift). Use this to check whether a route you remember from a past session still exists, or whether a new one has shown up, before assuming. |
| `/schema` | GET | `route` (optional URI filter), `examples` (bool, default true) | Machine-readable API contract for this running instance: route methods + summaries for all routes, plus explicit query schema/examples for selected high-risk write routes (`/flag`, `/par`, `/wire`, `/insert`). Use this as preflight validation input so agents can build correct calls on first try instead of probing. |
| `/smoketest` | GET (default), POST/PUT (when `writeTest=true`) | `writeTest` (bool, default false), `name` (optional examples DAT name) | Built-in functionality smoke check for the running bridge. Default mode is read-only and validates route registration, embedded docs, examples DAT parseability, schema coverage, and runtime state. Optional write mode performs a create/destroy probe and requires POST/PUT. Returns `{passed, checkCount, writeTest, checks[]}`. |
| `/cookstats` | GET | `paths` (explicit) or `path`/`family`/`recursive` (scan, same convention as `/errors`/`/flag`) | `{sampledAt, nodes: [{path, opType, totalCooks, cpuCookTime, gpuCookTime, cookedThisFrame}]}` — read-only cook-cost snapshot; call once, trigger a state change, call again, diff client-side. Deliberately doesn't sleep/wait server-side (would freeze the TD UI for the duration). |
| `/logs` | GET | `limit` (default 50) | Last N request log entries: `{time, method, uri, statusCode, callbackElapsedMs, …}` |

### Examples provenance and rebuild source

The examples served by `/examples`, `/examples.tsv`, and `/examples-refresh` are read from the embedded DAT `table_td_examples` inside `TdHttpApi`.

That embedded table ultimately originates from TouchDesigner's built-in OP Snippets catalog table:

- Loader tox: `Samples/Learn/OPSnippets/OPSnippetsOnDemand.tox`
- Master catalog table inside loader: `snippetsChooser/allAlphaNumeric`

Current lineage in this repo:

1. TD source table (`allAlphaNumeric`) was extracted.
2. Project cache TSV was created at `data/harness/op-snippets/catalog.tsv`.
3. Same dataset was embedded into `TdHttpApi` as `table_td_examples` for tox-only portability.

If you ever need to recreate from TD source again (not from the embedded DAT), use the workflow in [.ai/skills/td-network-craft.md](.ai/skills/td-network-craft.md) under “How the corpus was located” and “How to actually materialize a specific example (verified mechanism)”.

### Write / Mutate

| Route | Method | Key params | Returns |
|---|---|---|---|
| `/dat` | POST/PUT | `path`; body = new content | Overwrites DAT `text`/`csv`. Fails if not `isEditable`. |
| `/par` | POST/PUT | `path`, `par`, and `value` or `expr` | Updated `{name, mode, value, [expr]}` |
| `/create` | POST | `parent` (default: open network), `opType`, `name`, `x`/`y` (omit to auto-place), `inputs`, `viewer` | Node summary of the new operator |
| `/create-from-template` | POST | `template` (filename under `data/harness/network-templates/`, no `.json`), `parent`, `x`/`y`, `namePrefix`, plus one param per template slot | `{template, root, created: {localName: actualPath}}` |
| `/insert` | POST | `path` (downstream node), `input` (index, default 0), `opType`, `name` | Splices a new node into an existing connection: wires dest-input's current source → new → dest, and shifts dest + everything to its right by 200 to make room. Returns `{inserted, source, dest, input}` |
| `/wire` | POST | `path`, `inputs` (comma-separated, in order) | Node summary with updated input wiring |
| `/duplicate` | POST | `path` (single) or `paths` (preserves wiring), `name`, `x`/`y` or `dx`/`dy`, `parent` | Node summary (or list) of the copy/copies |
| `/move` | POST/PUT | `path`+`x`/`y` (absolute, single node) or `paths`+`dx`/`dy` (relative, group) | Updated node summaries |
| `/layout` | POST/PUT | `paths` (explicit set) or `parent` (default: open network, lays out **all** its children if `paths` omitted), one of `horizontal`/`vertical`/`gridRows` (default: `horizontal`) | `{parent, mode, count, nodes[]}` — `COMP.layout()`, the Python equivalent of TouchDesigner's Shift+L. Arranges ops into a clean, non-overlapping line/grid in wire order. See the verification discipline below — always scope `paths` tightly and re-check afterward. |
| `/delete` | POST/DELETE | `path` or `paths` | `{deleted: [paths…]}` (captured before destruction) |
| `/comment` | POST/PUT | `path` or `paths`, `text` (pass `""` to clear) | `[{path, comment}]` |
| `/flag` | POST/PUT | `name` (one of OP's boolean "Common Flags": `activeViewer`, `allowCooking`, `bypass`, `cloneImmune`, `current`, `display`, `expose`, `lock`, `python`, `render`, `selected`, `showCustomOnly`, `showDocked`, `viewer`), `value` (default `true`), plus `path`/`paths`/`family`/`recursive` targeting exactly like `/errors` | `[{path, <name>: <value>}]` — deterministic replacement for one-off `/run` scripts that toggle a Common Flag |
| `/bypass` | POST/PUT | `path`/`paths`/`family`/`recursive`, `value` (default `true`) | `[{path, bypass}]` — thin alias for `/flag?name=bypass`, kept for convenience |
| `/annotate` | POST | `paths` (nodes to enclose), `title`, `body`, `mode` (`networkbox`/`annotate`/`comment`), `pad` (default 40), `parent` | Node summary of the created `annotateCOMP` |
| `/select` | POST | `path` or `paths`, `home` (bool, default true), `zoom` (bool, default true) | Sets the TD UI's selection to these nodes and (unless `home=false`) navigates the network editor to their parent and homes on them. The write-side mirror of `/selected` — lets an agent direct the user's attention. Returns the selected node summaries. |
| `/save` | POST/PUT | `path` (optional, default: current project file), `saveExternalToxs` (bool, default `false`) | `{saved, path, saveExternalToxs}` — `project.save()`, the Ctrl+S equivalent. Doesn't touch external `.tox` files unless `saveExternalToxs=true`; see `/save-external-tox` to save just one external-tox-backed COMP. |
| `/save-external-tox` | POST/PUT | `path` (a COMP with a non-blank `externaltox` par), `recursive` (bool, default `false`) | `{path, externaltox, recursive, saved}` — `COMP.saveExternalTox()`. Saves that one COMP out to its already-configured external `.tox` file, independent of the project save and of whether the COMP is currently flagged dirty. |

### Execute / Utility

| Route | Method | Key params | Returns |
|---|---|---|---|
| `/run` | POST | Body: arbitrary Python script text | `{output, [error]}` — stdout redirected, tracebacks captured. TD globals (`op`, `ops`, `ui`, `project`, `me`) available. Best route for complex one-shot operations. |
| `/diff` | POST | Body: JSON `{"before": <network snapshot>, "after": <network snapshot>}` | `{nodes: {added, removed, changed}, wires: {…}, references: {…}}` |
| `/reload` | GET | — | `{reloaded: […], skipped: […]}` — hot-reloads project Python modules |


### Example calls

```bash
curl "http://127.0.0.1:3031/network?recursive=false"
curl "http://127.0.0.1:3031/dat?path=/project1/AppStore/execute1"
curl "http://127.0.0.1:3031/par?path=/project1/Test_Claude_Connections/comp_insta_template&par=prefit"
curl -X POST -d "" "http://127.0.0.1:3031/par?path=/project1/Test_Claude_Connections/comp_insta_template&par=prefit&value=fitoutside"
curl -X POST -d "" "http://127.0.0.1:3031/create?parent=/project1/Test_Claude_Connections&opType=nullTOP&name=null1&x=200&y=0&inputs=/project1/Test_Claude_Connections/comp_insta_template"
curl "http://127.0.0.1:3031/reload"
```

**Always pass a body on POST/PUT, even an empty one (`-d ""`).** Without it, curl sends no `Content-Length` header, and POCO's web server appears to wait for a request body before dispatching to `onHTTPRequest` — the wait times out around ~60 seconds before it processes the request anyway. Every route here reads its arguments from the query string, not the body (except `/dat`'s POST, which uses the body as the new content) — `-d ""` is just there to make the request well-formed, not because any data needs to go in it. This was the actual cause of a very confusing debugging session that initially looked like a TD cook-performance problem (a Feedback TOP loop happened to be running expensively at the same time, which was real but was a coincidental red herring — see below).

---

## Known gaps

- **POST/PUT without a body hangs for ~60 seconds.** See the note above under Example calls — always send `-d ""` (or real content) on write requests. This reproduces from any HTTP client, not just curl, and was confirmed to cause identical ~60s stalls from a completely separate agent harness — it's not specific to any one caller. If a route is mysteriously slow again, check `/logs` first: a `requestKeys` list missing `Content-Length` on a slow entry, alongside a tiny `callbackElapsedMs`, is the signature of this exact issue.
- **`localhost` costs ~200ms extra per request vs `127.0.0.1`** (measured: ~0.21s vs ~0.01s), almost certainly Windows trying IPv6 (`::1`) first and falling back to IPv4. Two orders of magnitude smaller than the POST-body issue above, but real and it stacks across many calls in a session — always use `127.0.0.1`.
- **Expression parsing is regex-based, not evaluated.** `_OP_EXPR_PATTERN` only catches literal `op('...')`/`opex('...')` string calls inside an expression. Dynamically-built references (`op(some_var)`) won't show up as a reference.
- **DAT script bodies aren't inspected for references.** A script DAT that calls `op('other1')` inside its Python body (as opposed to in a parameter expression) isn't walked — only parameter-level references are captured. Use `/dat` to read the script directly when you need that.
- **Bootstrapping caveat**: `config.ReloadModules()` reloads itself as part of its own module walk. If `config.py`'s `ReloadModules()` signature ever changes again (e.g. return shape), the *first* call after that edit will run on the stale cached version — needs one manual `td.reloadModules()` from the Textport to bootstrap, same as when `/reload`'s return-tuple support was first added.

## Templates

Reusable network patterns, extracted from analyzing a real hand-built network via `/network` and captured as data rather than left as one-off prose or a single live instance. Stored under `data/harness/network-templates/` (all agentic-collaboration tooling data lives under `data/harness/` — templates, the OP Snippets catalog, etc.).

| Template | File | Pattern |
|---|---|---|
| Simple feedback loop | `data/harness/network-templates/simple_feedback_loop.json` | Source → Transform → junction Null → {Feedback TOP (targets the downstream Composite) → Level TOP (decay)} + direct path, both feeding the Composite, → output Null. Analyzed from `/project1/Demo_Feedback`'s `moviefilein1` chain; rebuilt and verified via `/diff` in `/project1/Feedback_Template_Test`. |

**Schema**: `nodes[]` (each with `name`, `opType`, relative `x`/`y`, and optional `pars` — a par can be a literal `{"value": ...}`, an `{"expr": ...}` expression string, an `{"ref": "<template-local node name>"}` for OP-type params like a Feedback TOP's `top` that must resolve to another node *in this template* rather than a literal path, or a `{"slot": "<name>"}` placeholder resolved from the `slots` map at instantiation time), `wires[]` (`from`/`to`/`toInput`, using the template-local node names), and `slots` (named placeholders — e.g. `sourceFile` for the video path — with no sensible universal default, meant to be filled in per-instantiation).

**Instantiate one with `/create-from-template`** — e.g. `POST /create-from-template?template=simple_feedback_loop&parent=/project1/SomeComp&sourceFile=D:/path/to/video.mp4`. Verified to produce an exact structural match (same positions, params, wires, and references) to the hand-built reference instance. Node creation happens in a first pass (so every template-local name resolves to a real op before any `ref` gets applied), then pars, then wires.

## New Routes (Friction Point Fixes)

### GET `/pars?path=<node>` — Exhaustive Parameter Catalog

**Problem it solves:** When building networks programmatically, guessing parameter names leads to failed builds (e.g. `rad0` instead of `radx` on a `torusPOP`, `attscope` instead of `attribscope` on a `poptoCHOP`). The only way to discover the real names was a `/run` introspection round trip.

**Response:** JSON dictionary mapping every parameter name to a metadata object:

```json
{
  "radx": { "label": "Radius X", "page": "Torus", "mode": "EXP", "isFloat": true },
  "attribscope": { "label": "Attribute Scope", "page": "Common", "mode": "MENU", "isMenu": true, "menuNames": ["point", "prim", ...], "menuLabels": [...] }
}
```

**Usage pattern:** Before writing a multi-node build script, call `/pars` on each operator type about to be used. Surfaces all naming mismatches upfront in one batch, avoiding discover-one-failure-at-a-time loops.

### GET `/opinfo?opType=<type>` — Operator Schema (Wire Inputs & OP-Reference Parameters)

**Problem it solves:** An operator's external input signature isn't documented in the UI or accessible via Python params. A `poptoCHOP` takes its source via a `pop` parameter (not a wire), while most CHOPs expect wired inputs — there's no way to know which pattern without trial-and-error.

**Response:** JSON object with wire-input count and list of OP-reference parameters:

```json
{
  "opType": "poptoCHOP",
  "wireInputCount": 0,
  "opRefParams": [{ "name": "pop", "label": "POP", "allowMultiple": false }]
}
```

**Usage pattern:** Before `/create` and `/wire` in a build, query `/opinfo` for each node type. Decides deterministically whether to `/wire` or set a `/par` — no more guessing.

## Friction Points & Mitigations (Lessons from the Field)

Learned during live use of the API on a fresh project. These are already best-practice patterns, but worth elevating so future users don't re-discover them:

1. **Don't assume channel/attribute names; verify them.** Runtime operators like `poptoCHOP` generate channel names from config—they're not predictable from the UI alone (e.g. `nameformat=basic` may produce lowercase `p0`/`p1`/`p2`, not `P_0`). Always call `GET /chop` (or `/dat`) to read back the actual generated names before wiring a downstream reference to them.

2. **Download `/examples.tsv` once locally; don't query `/examples` repeatedly.** The `/examples?q=<term>` endpoint returns summarized/truncated JSON. For large result sets, use `curl -s .../examples.tsv > catalog.tsv` once, then `grep -i <term> catalog.tsv` locally. Faster, cheaper, and gives exact untruncated matches.

3. **Parse `/run` responses as `{output, [error]}` before inspection.** Improper parsing can send large responses to `temp` files, losing readability. The correct pattern: `curl ... | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('output') or d.get('error'))"`. Keeps output inline.

4. **Use `$TMPDIR` for temporary script files, not `/tmp`.** `/tmp` is sandboxed read-only in some environments. Always default to `os.environ.get('TMPDIR')` for any local scratch file.

5. **Use `/network` for introspection, not custom `/run` walking.** The API already provides `GET /network?path=<comp>&recursive=true` for full structure with utility-node resolution. Don't re-implement tree-walking and param serialization in a `/run` script — that's a code smell that a new route should be born.

6. **Don't mix `/tmp` and project-local `tmp/` directory.** When creating temporary `/run` script files, always use `tmp/` (the project-local directory), never `/tmp` or system temp. Mark them with a distinct prefix (`td_run_<purpose>.py`) and delete after verification.

7. **Batch parameter introspection before building.** If a build will create multiple different node types, run `/pars` for all of them in one pass (via `/run` if needed) before the first `/create`. Discovers naming conflicts upfront.

## Roadmap / ideas not yet built

- **`/checkpoint` + `/restore` (JSON-based, not `.tox`)** — discussed but not yet built. Design: a checkpoint is the same node/wire/par schema `instantiate_template()` already knows how to replay, but capturing *every* param (not just non-default ones, per `_get_customized_pars`) plus DAT text/csv content for every node in a COMP. Restore = delete the COMP's current children, replay the checkpoint through the same instantiation logic `/create-from-template` uses. Tradeoff: won't be as bit-perfect as a real `.tox` (extension state, some exotic built-in flags might not round-trip) — good enough for "undo my last batch of agent edits," not a full project-level backup replacement.
- **SVG renderer using real node positions** — `nodeX`/`nodeY`/`nodeWidth`/`nodeHeight` are now available (see `/network` and `/bounds`); Mermaid still can't take explicit coordinates (auto-layout only), so a pixel-accurate view of the actual TD layout would need a dedicated SVG route.
- **Real graph-aware auto-layout** — `/create`'s `_auto_place` is a local one-node-at-a-time heuristic (right of inputs, nudge to avoid overlap). It doesn't consider the whole chain's shape (branches, loops), so a multi-node build can still come out layout-ugly even though no individual node overlaps anything — worth checking `/network` after a multi-step build rather than assuming clean. In particular it doesn't yet know the fork/rejoin lane-widening rule above — that's applied by hand today.
- **Script-body reference scanning** — extend reference detection into DAT text content, not just parameter expressions.
- **Auth or a localhost-only bind check**, if this server ever needs to run somewhere less trusted than a single dev machine.

## See Also

- [.ai/skills/td-network-craft.md](.ai/skills/td-network-craft.md) — learning idiomatic network-building technique from the official OP Snippets corpus using this tooling; home of the snippet catalog and verified craft notes.
- [.ai/skills/td-common-mistakes.md](.ai/skills/td-common-mistakes.md) — Reference for avoiding common TD Python, parameter, and callback mistakes.
- [.ai/skills/td-skills.md](.ai/skills/td-skills.md) — Meta-skill for TouchDesigner AI assistance, API hierarchies, and documentation.
- [.ai/skills/td-appstore.md](.ai/skills/td-appstore.md) — the AppStore extension, one of the first real networks this tool was used to explore
- [.ai/skills/td-vscode-python-environment.md](.ai/skills/td-vscode-python-environment.md) — module import scheme (`import td_util`), `td.reloadModules()`, and why TD types cause errors during reload
- **td-docs-mcp** — The specialized Model Context Protocol (MCP) server used to retrieve live, up-to-date documentation and references for TouchDesigner Python operators and classes.
