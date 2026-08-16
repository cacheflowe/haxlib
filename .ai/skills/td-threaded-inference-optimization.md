---
name: td-threaded-inference-optimization
description: Threading and background work patterns for running inference on ONNX models and other ML tooling in TouchDesigner. Use this when you want to optimize inference performance and avoid dropped frames in a live TouchDesigner project.
---

# Threading Optimization: MoveNet Pattern for ONNX Inference

## Summary

Restructuring where preprocess/postprocess run relative to the background inference thread yielded a **massive performance gain** — from ~15-20 FPS to **70+ FPS** — with no changes to the actual inference or processing logic.

## The Problem (Before)

The original `ONNXInferenceManager` base class spawned a background thread that did **everything**:

```
Main Thread (onCook):
  - nA.copy()  ← copy TD's GPU staging buffer (required because bg thread can't read it safely)
  - Spawn thread

Background Thread:
  - preprocess(nA_copy)   ← 25-97ms (cache-cold numpy array from GPU staging buffer copy)
  - session.run()          ← ~16ms (CUDA inference)
  - postprocess(outputs)   ← 0.3-2ms
  - [thread holds is_inferencing=True for total duration: 40-115ms+]

Main Thread (next frames):
  - Skips frames while bg thread is busy → low effective FPS
```

**Key issues:**
1. `nA.copy()` was needed because the background thread couldn't safely read TD's GPU staging buffer
2. The copy itself was slow, and the bg thread reading the copied array still had cache misses
3. The thread held `is_inferencing=True` for the entire pre+infer+post duration, causing many skipped frames
4. Postprocess on the bg thread required thread-safety locks (e.g., `tracker_lock` in YOLO26)

## The Discovery

MoveNet's standalone implementation (`tox/MovenetONNX.py`) used a different pattern and ran significantly faster. The key difference: **only `session.run()` runs on the background thread**.

## The Solution (After)

Restructured `ONNXInferenceManager.onCook()` and `_inference_thread()` to match MoveNet's pattern:

```
Main Thread (onCook):
  1. Check for pending raw outputs from previous frame's bg thread
  2. If found: postprocess(raw_outputs) → copyNumpyArray → output
  3. If not inferencing: preprocess(nA) → store input tensor → spawn bg thread

Background Thread:
  - session.run() ONLY  ← ~16ms
  - Store raw outputs in pending_result

Main Thread (next onCook):
  - Pick up raw outputs, postprocess, output
```

## Why This Is So Much Faster

### 1. No `.copy()` needed
Preprocess now runs on the main thread, reading directly from TD's GPU staging buffer while it's cache-warm. The background thread never touches the raw TD buffer.

### 2. Background thread occupies minimum time
Previously: `is_inferencing=True` for 40-115ms+ (pre+infer+post)
Now: `is_inferencing=True` for ~16ms (infer only)

This means far fewer frames are skipped between inferences. The main thread can start a new inference almost every other frame instead of every 4-7 frames.

### 3. No thread-safety locks needed
Since postprocess runs on the main thread, there's no concurrent access to tracking state, table DATs, or other TD operators. Locks like `tracker_lock` in YOLO26 were removed entirely.

### 4. TD operator access is safe
Postprocess can directly write to Table DATs, update parameters, etc. without queuing or deferred updates.

## Files Changed

- **`python/onnx_inference_manager.py`** — Base class restructured:
  - `_inference_thread()`: Now only runs `session.run()`, stores raw outputs in `self.pending_result`
  - `onCook()`: Preprocess before thread spawn, postprocess when results arrive, removed `nA.copy()`
  
- **`python/script1_callbacks_yolo26_obj_det.py`** — Removed thread-safety overhead:
  - Removed `import threading`
  - Removed `self.tracker_lock = threading.Lock()`
  - Removed `with self.tracker_lock:` from `postprocess()` and `write_tracks_to_table()`

## Results

| Metric | Before | After |
|--------|--------|-------|
| Effective FPS | ~15-20 | **70+** |
| BG thread busy time | 40-115ms | ~16ms |
| Frames skipped per inference | 4-7 | 0-1 |
| Thread-safety locks needed | Yes | No |
| nA.copy() required | Yes | No |

## Applying to Other Scripts

This pattern should be applied to any ONNX inference script in the project. Scripts that already use `ONNXInferenceManager` as a base class (like Depth Anything) automatically benefit from the base class change. Standalone scripts need manual restructuring:

- **`script1_callbacks_yunet.py`** — Standalone (uses cv2.FaceDetectorYN, not ONNX Runtime). Could benefit from the same pattern if restructured to use a bg thread for `detector.detect()`.
- **`tox/MovenetONNX.py`** — Already uses this pattern (it was the inspiration). No changes needed.
- **Any future ONNX scripts** — Should extend `ONNXInferenceManager` to get this pattern for free.

## Rule of Thumb

> **Only `session.run()` (or equivalent blocking inference call) should run on the background thread.** Everything else — reading input textures, preprocessing numpy arrays, postprocessing outputs, writing to TD operators — belongs on the main thread.

## Round 2: Persistent Worker Thread + Input-to-Output Latency Tuning

A later pass on `python/util/onnx_inference_manager.py` (during `onnx_rfdetr_seg.py`'s development) tightened things further, past raw throughput and into **input-to-output latency** — the gap a network's own cache/cacheselect "Framedelay" mechanism has to compensate for so a delayed raw-video passthrough visually lines back up with its corresponding detection/mask output.

### Persistent worker thread instead of spawn-per-frame

The pattern above still spawned a **brand-new `threading.Thread` every single frame** for the `session.run()`-only call. `onCook()` now instead:

- Lazily starts **one** long-lived worker thread (`_ensure_worker_started()`) that blocks on a `queue.Queue(maxsize=1)` between frames.
- Submits work via `self._work_queue.put_nowait(input_tensor)` instead of constructing a new `Thread` object.
- The `maxsize=1` queue enforces the same "only one inference in flight" invariant the old code got for free from `is_inferencing` gating — `onCook()` never submits new work while a previous item is still unconsumed, so `.put_nowait()` never raises `Full`.

This removes OS thread-creation overhead from the per-frame budget. It's a real but modest win on its own — the bigger latency wins below came from elsewhere.

**Known tradeoff:** if a script's Callbacks DAT is live-edited/resynced while TD is running, the module re-executes and creates a **new** manager instance with its own new worker thread; the old instance's thread has no shutdown hook tied to that reload and sits blocked forever on an empty queue (`daemon=True`, near-zero cost, dies with the TD process). Accepted as a minor leak on manual script edits, not something that compounds during normal use.

**This rename silently broke a subclass that overrode the OLD per-frame thread method by name, and it went unnoticed for a long time.** `onnx_yunet.py` predates this round and originally overrode whatever the per-frame worker method was called before this rename (its own docstring still called it `_inference_thread()`, reimplementing the entire timing/locking/exception-handling loop that now lives in `_worker_loop()`). When the base class was renamed to `_worker_loop()`, that override silently stopped being an override at all — Python doesn't warn about defining a method that doesn't match anything in the base class, it just becomes dead code. Every subsequent call fell through to the (unrelated) subclass's inherited default `run_inference()`, which calls `self.session.run(...)` — but YuNet's `self.session` is a `cv2.FaceDetectorYN` object (loaded via OpenCV's DNN module, not `onnxruntime`), which has no `.run()` method at all. This produced a clean, immediate `AttributeError: 'cv2.FaceDetectorYN' object has no attribute 'run'` every single inference call — but since nothing exercised this script live for a long stretch, it sat broken undetected until someone finally ran it again. **Fix:** override `run_inference(self, input_tensor)` instead (the base class's actual, current, purpose-built extension point for "anything `session.run()` can't express directly" — see `run_inference()`'s own docstring, and `onnx_rvm_seg.py` for another real example) rather than reimplementing the whole worker loop; `_worker_loop()` already wraps that call with its own timing/locking/exception handling, so the override can be a single line (`return self.session.detect(input_tensor)[1]`-equivalent).

**Takeaway:** when refactoring a base class's internal method that subclasses are expected to override, grep the WHOLE project for every subclass calling itself out as overriding that specific old name before renaming/removing it — a docstring like "Overrides ONNXInferenceManager.X()" is a load-bearing claim, and a silently-dead override produces no warning, no error, no visible symptom at all until the exact code path it used to intercept actually runs again.

### CUDA execution provider tuning — a regression, not a win

Also added: explicit CUDA EP options via `onnx_util.providers()`, including `device_id` and (briefly) `arena_extend_strategy='kSameAsRequested'`.

**The `arena_extend_strategy` change was a measured regression**, not an improvement, despite sound-sounding reasoning going in ("every script here has a fixed input shape, so ORT's default doubling-growth arena buys nothing"). Live A/B on `rf-detr-seg-nano.onnx`:

| | Effective FPS | Framedelay needed |
|---|---|---|
| Default (`kNextPowerOfTwo`) | ~80s | 4 |
| `kSameAsRequested` | mid-50s | 6 (regressed) |
| Reverted to default | ~89-96 | back down |

Root cause: `arena_extend_strategy` controls how the CUDA arena **grows** when it needs more memory than currently cached, not whether it reuses memory at all. If a model's actual internal allocation pattern isn't byte-identical every call, `kSameAsRequested` forces the arena to re-extend (a real, synchronizing `cudaMalloc`) far more often than the default, which rounds generously and rarely needs to re-extend at all. **Lesson: don't adopt an ORT tuning knob from reasoning alone — measure the isolated effect before keeping it.** `device_id` (harmless, and the only GPU on this machine anyway) was kept; `arena_extend_strategy` was reverted and the module docstring now records the measured outcome instead of the original (wrong) justification.

### `numpy_array_delayed` — processing latency vs. content staleness are different things

Added a live-toggleable `self.numpy_array_delayed` instance attribute controlling the `delayed=` argument to `scriptOp.inputs[0].numpyArray(delayed=...)`:

- **`delayed=True` (default):** avoids a CPU/GPU sync stall by accepting whatever frame TD's async GPU→CPU download queue happens to have ready. Per TD's own docs, this returns "the image that was 'current' on the *previous* call" — under load, that queue can be staler than "just 1 frame old."
- **`delayed=False`:** forces a synchronous wait for the *actual current* frame's render+download to finish.

A `Pipelineframes` diagnostic was added (self-installing read-only par next to the existing `Effectivefps`, on the parent COMP) that records `absTime.frame` at capture time and again when that same result is pushed to output — an exact, absolute frame-count measurement of the script's own capture→output latency, not an ms-based estimate.

**The trap:** `Pipelineframes` measures latency **starting from the moment the script receives the array** — it says nothing about how stale that array's *content* already was. Flipping to `delayed=False` made `Pipelineframes` read *worse* (1.0 → 2.0 frames) and dropped average FPS (~89 → ~63), which initially looked like a clear regression and was reverted on that basis. **That was the wrong conclusion.** The user's own visual sync test told a different story: with `delayed=False` actually held in place, the network's `Framedelay` requirement dropped from 6 to 3 frames — a real, large latency win invisible to the instrumentation, because the synchronous stall trades "fast to fetch, but staler content" for "slower to fetch, but fresher content," and total end-to-end latency is content-staleness *plus* processing time, not processing time alone.

**Lesson: a metric that only measures post-receipt processing time cannot detect an improvement (or regression) in how stale the received data was.** When a change trades one kind of cost (stall duration) for another (queue staleness), a single narrow metric can point the wrong way — trust an end-to-end/visual measurement of the thing you actually care about over a component-level proxy metric.

`numpy_array_delayed` is **not** flipped as the base-class default — it's set per-script (`onnx_rfdetr_seg.py`'s `__init__` sets `self.numpy_array_delayed = False` after confirming the win). Other scripts (heavier models, tighter frame budgets) haven't been re-verified against this tradeoff and could regress from the added stall if their own margin is tighter.

### Verifying "no global impact" — external polling is too coarse, measure inside TD instead

To confirm a per-script stall wasn't dragging down the rest of the app (other networks, UI, audio), an external HTTP-polling loop checking `absTime.step` (>1 means TD dropped a frame) was tried first and was **too coarse** — each poll is a fresh HTTP round-trip with no relationship to TD's own frame clock, so it can easily miss a single-frame hitch entirely.

The reliable approach: a temporary `baseCOMP` containing a `performCHOP` (with its `droppedframes`/`timeslicestep` channels explicitly enabled — they're off by default, per-channel toggle pars) and an `executeDAT` with **`framestart` explicitly enabled** (its own toggle, separate from the DAT's `active` par) accumulating a running total into `parent().storage` on every real `onFrameStart`. Read the accumulated total back after a real time window (not per-poll) and destroy the probe when done. This caught every one of ~1,332 real frames over 15 seconds and confirmed zero dropped frames / zero time-slice-step-over-1 events — a number an external poll loop could never have proven with confidence.

## Rule of Thumb (Round 2)

> When A/B testing a performance change, measure the thing you actually care about end-to-end (or get the user's real visual/perceptual read on it), not just a component-level proxy metric — a narrow measurement can point the wrong way when a change trades one kind of cost for another. And when verifying "no regression elsewhere," instrument *inside* the running process (an accumulator over every real frame) rather than polling from outside at an unrelated cadence.

## Round 3: `run_inference()` overrides run on the worker thread too — and it crashed TD

`onnx_rvm_seg.py` (RVM video matting) was the first script to override `run_inference()` (see the base class's extension point, added for this script — the default implementation just wraps `session.run()`; an override can replace it entirely, e.g. for IOBinding-based invocation). That override needed to read a custom par each frame (`Downsampleratio`, so the user can tune it live) and called the same `_par_or_default(name, default)` helper every other script in this project already uses safely from `preprocess()`/`postprocess()`:

```python
def _par_or_default(self, name, default):
	if self.scriptOp and hasattr(self.scriptOp.par, name):
		return getattr(self.scriptOp.par, name).eval()  # <-- TD parameter access
	return default
```

Calling it from inside `run_inference()` **crashed TouchDesigner entirely**, not just a Python traceback. The reason: `run_inference()` executes on the persistent worker thread (see Round 2's `_worker_loop()`), and `_par_or_default()` calls `self.scriptOp.par.<name>.eval()` — a genuine TD operator access. This is exactly the violation `.ai/skills/td-threading.md` warns about ("never access `op()`, `me`, `parent()`, or any TD object from a thread — crash or undefined behavior"), it just wasn't obvious at the call site because `_par_or_default()` *looks* like a harmless plain-Python helper — every other script only ever calls it from `preprocess()`/`postprocess()`, both of which are main-thread by this architecture's design, so the helper itself was never the problem before.

**The fix:** read the par in `preprocess()` (main thread, safe) and stash the plain value as an instance attribute; `run_inference()` (worker thread) reads that attribute instead of ever touching `self.scriptOp`:

```python
def preprocess(self, nA):
	...
	# Read on the main thread -- run_inference() must never call self.scriptOp/par
	# directly, see the Round 3 writeup in this doc for why.
	self._current_downsample_ratio = np.array(
		[self._par_or_default('Downsampleratio', DOWNSAMPLE_RATIO)], dtype=np.float32
	)
	return self._input_tensor_buf

def run_inference(self, input_tensor):
	downsample_ratio = self._current_downsample_ratio  # plain attribute, safe cross-thread
	...
```

**Lesson: a helper method's safety depends on which thread calls it, not on what the method itself does.** `_par_or_default()` didn't change and isn't itself broken — moving the *call site* into a new thread context (writing a `run_inference()` override, the one place in this codebase's architecture that runs on the worker thread) silently made an existing, previously-always-safe helper dangerous. Before adding **any** code to a `run_inference()` override, audit every method it calls (transitively) for TD object access — don't assume a helper is safe just because it's used safely elsewhere in the file.

## Round 4: recurrent state and resolution changes — self-heal, don't just avoid

RVM (and any other recurrent/stateful model added later) carries per-frame hidden state forward across calls. That state's *shape* is tied to whatever input resolution produced it. Two related failure modes surfaced together during development, both worth designing against up front for any future stateful model, not just reacting to after a crash:

1. **A live resolution change invalidates old state.** This project's video networks commonly drive their working resolution from a `switch1` cycling between clips of *different aspect ratios* — a completely normal, expected runtime event, not an edge case. The very first frame after such a switch fed the old-resolution recurrent state into the new-resolution graph and threw `Expand`/shape-verification `RuntimeError`s from ONNX Runtime. Fix: detect the shape change where the new frame is captured (`preprocess()`, main thread) and flag a state reset; consume that flag and actually reset (back to the model's documented broadcastable zero state) at the start of the next `run_inference()` call.
2. **Even without an external resolution change, don't assume a stateful model's recurrent shape is perfectly deterministic frame-to-frame.** A shape mismatch (`{1,64,3,5}` vs `{1,64,4,5}`) was observed live between two consecutive frames with no detected resolution change — never fully root-caused (a rounding instability somewhere in the model's own internal downsampling is the leading suspect), but the practical fix doesn't require knowing the exact cause: wrap the inference call in a try/except, and on a shape-related `RuntimeError`, reset state and retry once. A dropped frame of temporal consistency is a trivial cost; a script wedged in a repeating per-frame error loop is not.
3. **A *large* resolution change (not just a live source's aspect ratio) needs more than a state reset — the IOBinding's output bindings need recreating too.** Recurrent-state reset alone recovered fine from a same-scale aspect shift (e.g. 312x175 -> 312x234, different video clips at a similar working size), but tuning `Inputwidth` from 312 to 960 (a genuinely large jump) kept erroring every frame even after a state reset — only a fresh `session.io_binding()` (re-binding `fgr`/`pha`/`r1o..r4o` outputs again) recovered. Since there's no cheap, reliable way to distinguish "small aspect shift" from "large resolution change" at the point a mismatch is detected, and recreating an `io_binding` is cheap, do both together on every detected shape change rather than trying to pick the lighter fix per case.
4. **Watch initialization order when a helper method is reused across two different lifecycle points.** A method built to recreate the `io_binding` (for reason 3 above) was also called from `on_model_loaded(session)` — but `ONNXInferenceManager`'s base class calls `on_model_loaded(session)` **before** assigning `self.session = session`, specifically so a subclass can validate before the "official" session is live. A helper that reads `self.session` (needed since it's also called later from `run_inference()`, where there's no local `session` parameter to use) silently gets `None` there, and every single model load failed with `'NoneType' object has no attribute 'io_binding'`. Fix: explicitly set `self.session = session` at the top of `on_model_loaded()` before calling any shared helper that expects it — harmless, since the base class assigns the same object again right after.

**Lesson: for any recurrent/stateful model, build both an explicit reset trigger (on a detected shape/resolution change) *and* a defensive catch-reset-retry around the actual inference call** — treat "the state might not match this frame" as a normal, expected runtime condition to self-heal from, not just something to avoid by careful setup (the switch1/aspect-ratio case proves you can't always fully anticipate it ahead of time) — **and when a fix needs a helper shared across two different lifecycle callbacks, check what state each callback actually guarantees is set at the point it runs, not just at the point you're used to calling the helper from.**

## Round 5: naive batching regressed a two-stage pipeline — dynamic batch size re-triggers CUDA's algorithm search

`onnx_hsemotion.py` (SCRFD face detector + HSEmotion classifier) is a genuinely different shape from every other script here: it's **two models**, and the second one (emotion classification) runs once per *currently tracked face* — a variable count, not a fixed one. The obvious optimization — batch all N face crops into one `session.run()` call instead of N separate calls — made things **dramatically worse**, not better: `postprocess()` spiked to 650-670ms (vs. ~19ms for the original naive per-face loop) on every frame that actually classified.

**Root cause, isolated with a standalone timing sweep** (call the same session repeatedly with `N = 1, 2, 3, ..., 4, 5, 10, 3, 7, 9` and print each call's wall time): the **first** call at any given batch size took 3.6-5.7 **seconds**; a **repeat** call at an already-seen size took ~10ms. ONNX Runtime's CUDA EP (via cuDNN) performs an expensive one-time convolution-algorithm search the first time it sees a given input shape, then caches that choice for later calls with the *same* shape. The original naive per-face loop never noticed this because every call was always shape `(1, 3, 260, 260)` — the cache warmed up once, on the very first face, ever. Batching by the *actual* tracked-face count meant the shape was `(N, ...)` where N changes almost every frame (faces come and go), so nearly every classification frame hit a brand-new shape and repaid that multi-second tax from scratch.

**Fix:** pad every batched call to one **fixed** ceiling size (`MAX_BATCH_FACES`, e.g. 16) with zero-filled dummy crops, so the shape never varies regardless of the real face count that frame; only read back the first N (real) results. This keeps the actual win (one call instead of N) while letting the algorithm-search cache warm up exactly once for the whole session's lifetime. Also worth knowing: ORT's CUDA provider options include `cudnn_conv_algo_search` (`'EXHAUSTIVE'` default, vs. `'HEURISTIC'`/`'DEFAULT'`) — switching that could shrink or remove the per-shape warmup cost directly as an alternative/complementary lever, not evaluated here since fixed padding fully solved this specific case.

**This is the same underlying ONNX Runtime behavior as Round 4's RVM resolution-change issue, wearing a different hat.** Round 4 was about a **recurrent model's io_binding/output buffers** needing to be shape-aware; this is about a **stateless model's convolution kernel selection** being shape-aware. Both are instances of one general rule:

> **ONNX Runtime's CUDA EP caches expensive setup work (kernel/algorithm selection, buffer allocation) per exact input shape. Any input whose shape varies at runtime — a recurrent model's working resolution, or a per-frame variable batch size across N detected instances — pays a real, sometimes severe, first-time cost every time that shape changes, not just once at model load.** Design for this up front in any future multi-instance-per-frame or dynamic-resolution integration: either keep the shape constant (pad to a fixed ceiling, as here) or explicitly accept and budget for a warmup cost on every genuine shape change (as Round 4's RVM fix does, since padding a recurrent state to a fixed resolution isn't practical the same way).

**Rule of Thumb (Round 5):** before trusting that "batch N items into one call" is strictly faster than "N separate calls," check whether N is fixed or varies at runtime. If it varies, verify with a standalone timing sweep across several different N values (repeating a few) before deploying — a single dynamic dimension can silently turn a batching "optimization" into a severe regression.

## Round 6: DRY sweep — shared helpers every `onnx_*.py` script should use instead of re-copy-pasting

A cross-script survey (2026-08) found the same handful of patterns copy-pasted near-verbatim into every one of this project's ~9 `onnx_*.py` scripts. All now live in one shared place — **new scripts should call these, not redefine local copies**:

- **`self._par_or_default(name, default)`** — now a method on `ONNXInferenceManager` itself (`python/util/onnx_inference_manager.py`). Every subclass inherits it; don't add a local copy.
- **`object_tracker.track_color(track_id)`** — deterministic golden-ratio-hue RGB per track_id, for per-track debug-draw coloring.
- **`object_tracker.prune_stale(active_ids, *state_dicts)`** — deletes entries for any track_id not in `active_ids` from each of the given per-track state dicts (box/landmark/keypoint/emotion/presence/etc.) — replaces the repeated `for tid in list(d.keys()): if tid not in active_ids: del d[tid]` loop, one call per script regardless of how many state dicts it tracks.
- **`object_tracker.box_smooth(state_dict, track_id, box, smoothing)`** — the standard EMA box-position/size lerp (seed on first sight, lerp toward `box` by `smoothing` after); returns the smoothed list.
- **`object_tracker.track_fade(lost_frames, track_buffer)`** — opacity multiplier (0.3-1.0) for drawing a currently-lost/predicted track, floored so it never goes fully invisible.
- **`object_tracker.td_to_px(td_x, td_y, width, height)`** — TD-space (bottom-up Y, 0-1 normalized) to top-down pixel coords, for cv2 drawing.
- **`onnx_util.check_providers(printfn, session)`** — the "log active providers, warn if CPU-only" tail every `on_model_loaded()` override had, standalone (pass `self.printONNX` as `printfn` to keep the `[ONNX]` prefix). The model-specific I/O-shape logging/sanity-checks around it stay in each script's own `on_model_loaded()` — only this generic tail moved.

**Deliberately NOT unified**, because the apparent duplication either has subtle behavioral differences or hasn't been verified to be truly identical:
- `_rotation_matrix_to_euler` (byte-identical between `onnx_yunet.py` and `onnx_mediapipe_face.py`) is safe to share, but the surrounding geometric/solvepnp head-pose functions around it have independently-discovered, never-cross-verified sign conventions — merging risks silently importing one script's fix into the other's untested convention.
- The isotropic box-size correction formula (`onnx_opencv_hands.py`/`onnx_mediapipe_face.py`, see `docs/learnings/debug-comp-camera-aspect.md`) is a strong extraction candidate (same fix, same root cause, applied twice) but wasn't moved in this pass — do a line-for-line diff of both call sites first.
- Per-script `write_tracks_to_table()` methods, `Confthreshold`/`Lowconfthreshold` collapsing in `onnx_yolo26_pose.py` only, and the `MAX_BATCH_*` padding patterns (see Round 5 above) all look similar but solve genuinely different problems per script — left alone.

**Gotcha hit while reloading scripts after this refactor, worth knowing for any future live-reload of a Callbacks DAT**: reading a script file with plain `open(path, 'r')` (no explicit encoding) in TD's embedded Python, then assigning the result to a synced Text DAT's `.text`, can **corrupt the file on disk** if the file has a UTF-8 BOM — Windows' default codepage decodes the BOM's raw bytes as three separate cp1252 characters instead of recognizing it as a BOM, and TD's own `syncfile` write-back then re-encodes those three wrong characters back into a mangled multi-byte prefix, breaking the file's very first line with a `SyntaxError` on the next load. **Always open with `encoding='utf-8-sig'` explicitly** when reading a script file for this purpose — it strips a BOM if present and decodes correctly either way. If a file already shows this corruption (a `SyntaxError: invalid character` pointing at line 1), the fix is a plain byte-level strip: read the file as `bytes`, drop the mangled prefix (a real BOM `EF BB BF` immediately followed by its own re-encoded mangling, 9 bytes total), and write the remainder back — confirm with `python -m py_compile` before reloading again.

## Round 7: the leaked worker thread from Round 2 wasn't "near-zero cost" at all — it pins the OLD manager's GPU memory forever, and repeated script reloads during active development exhausted the entire GPU

**Symptom, reported directly by the user**: "when working on the onnx code, we seem to hit a wall fairly frequently where the entire project bogs down and I have to restart... this seems to happen when we save a lot, because the onnx models are reloading, and something is building up... touchdesigner is currently using 100% GPU and all of our dedicated GPU memory." Confirmed via `nvidia-smi`: 15709/16376 MiB used (96%), 100% utilization, across a single dev session that had involved ~30-40 live script reloads (edit a `.py` file, push it into the live Callbacks DAT to test).

**Root cause, confirmed directly rather than assumed**: `threading.enumerate()` inside TD's own Python found **20 separate `_worker_loop` threads alive simultaneously**, when at most ~9 should exist (one per currently-active ONNX script). Round 2's own "known tradeoff" note had already identified the mechanism years earlier but seriously underestimated its cost: every script reload creates a brand-new manager instance with its own new worker thread; the OLD instance's worker thread is left blocked forever on `self._work_queue.get()` with no shutdown signal ever sent. **A blocked-but-alive thread's own stack frame holds a live reference to `self`** (the bound method it was started with) — Python's reference-counting GC cannot collect an object a live thread might still touch, so the ENTIRE old manager instance stays reachable forever, including its loaded `ort.InferenceSession`(s) and every byte of GPU/CUDA memory arena they hold. Confirmed by resolving each zombie thread's owning instance via `thread._target.__self__` (a private but stable CPython attribute) and cross-referencing against each live script's actual current manager (via each Callbacks DAT's own `cb.module.inference_manager`) — 13 of the 20 threads belonged to instances no live script referenced anymore.

**Immediate relief, measured**: manually sending each zombie thread's queue its already-implemented (but never-used) `None` shutdown sentinel, and clearing any `ort.InferenceSession`-typed attribute on each zombie's owner via introspection, dropped GPU memory from **15709 MiB → 6404 MiB** and utilization from **100% → 41%** within seconds — no TD restart needed. This alone is worth knowing as a live incident-response technique, independent of the permanent fix below (see the actual technique in the fix section — it's the same mechanism, just also usable ad hoc via `/run` against a frozen project without any code changes at all).

**Permanent fix**: added `ONNXInferenceManager.shutdown()` — sends the shutdown sentinel (`_worker_loop()`'s `while True` loop already checked for `None` and returned; it just never actually received one) and clears every `ort.InferenceSession`-typed instance attribute via `isinstance` introspection (so a subclass with its own extra session, like the face/hand scripts' landmark session or HSEmotion's emotion session, doesn't need to remember to add its own cleanup). Every `onnx_*.py` script's "Create global instance" section now calls `.shutdown()` on the PREVIOUS instance before constructing a new one.

**The first attempt at "find the previous instance" was wrong, and confirmed wrong live, not assumed**: the obvious approach — `_prev = globals().get('inference_manager')` at module level, before overwriting it — silently never found anything. Reassigning a Callbacks DAT's `.text` (the exact mechanism every live-reload in this project uses) gives the re-executed module code a **genuinely fresh `globals()` namespace**, not the same one from the previous execution — directly disproving what Round 2's own original note assumed ("the module re-executes and creates a new manager instance," phrased as if it were the same module object with the same globals).

**The SECOND attempt was also wrong, and this one caused a real TD crash, not just a missed fix.** Reasoning that TD's per-COMP `store()`/`fetch()` mechanism is specifically designed to survive script recompilation (true), it was used to hold the live manager instance directly: `parent().store('inference_manager_ref', inference_manager)`. This is wrong because TD's Storage is meant for data that gets **serialized with the project** — it needs to be picklable — and a live `ONNXInferenceManager` instance holds fundamentally unpicklable resources: a `threading.Thread`, a `threading.Lock`, a GPU-resident `ort.InferenceSession`. Storing it live risked TD attempting to persist that object, and shortly after this was deployed, TD crashed; on restart, one script's model began reloading in a continuous, never-ending loop. TD crashed a SECOND time while investigating, specifically while calling `.unstore()` to clean up the same stored object — strong direct evidence that touching that live object through TD's Storage system (not just the earlier `store()` call itself) was the unsafe operation, not a coincidence.

**Actual fix: a plain Python module-level registry inside `onnx_inference_manager.py` itself** (`_manager_registry`, a dict keyed by `parent().path`, with a `shutdown_and_register(comp_path, new_manager)` helper) — never serialized with the project (it's a regular imported module's global, not COMP Storage), so it can't be a save/crash vector, while still surviving a single script's Callbacks DAT recompilation (the base module itself isn't re-executed just because one script's DAT resyncs). Confirmed live, twice: (1) the crash did not recur across a save with the registry-based version deployed, and (2) reloading a script showed the worker-thread count staying flat across a reload (2 before, 2 after) with the OLD thread's id gone and a NEW one in its place — the intended behavior, achieved without ever touching TD's Storage system for this purpose.

**One transitional gotcha specific to developing this fix live (won't recur once deployed)**: reloading the *base class* (`onnx_inference_manager.py`, a real imported module) requires the separate `/reload` endpoint (`config.ReloadModules()`), NOT a Callbacks-DAT `.text` reassignment — forgetting this meant `shutdown()` didn't exist yet on already-running instances, producing `AttributeError: 'XInference' object has no attribute 'shutdown'`. This is a one-time artifact of changing the base class and its callers in the same live session; a project that adopts this fix from a clean start never hits it.

**Takeaway (this one specifically): a "this survives recompilation" property is necessary but not sufficient for choosing a storage mechanism — also ask what that mechanism is FOR, and whether what you're storing satisfies that contract.** TD's Storage is for project-persistent, picklable data; a live thread/lock/session bundle is neither project-persistent (it should die with the process) nor picklable, and using a technically-compatible-looking API for the wrong purpose produced a genuine two-crash incident, not just a missed optimization. When in doubt, a plain module-level Python object scoped to the lifetime of the process is the safer default for anything that must NOT survive a save/reload cycle.

**Verification**: directly (not by inference) confirmed the exact mechanism end-to-end — grabbed a specific zombie thread's owner via `_target.__self__`, called `owner._work_queue.put_nowait(None)`, and confirmed `thread.is_alive()` flipped from `True` to `False` within 1.5 seconds. (An earlier verification attempt wrongly concluded the fix didn't work, because it checked `is_alive()` immediately after sending the sentinel with no delay at all — the thread needs a brief moment to wake from its blocking `.get()` and execute its own `return`. Don't check thread death with zero delay.)

**Takeaway:** a "known, accepted, near-zero-cost tradeoff" comment is only as good as the analysis behind it — this one was flagged years earlier but never actually measured against a realistic number of accumulated reloads, and the true cost (an entire GPU's memory, not "a blocked thread") only became visible under the exact workload (heavy live-editing during active development) that the original note explicitly waved off as fine. When a "this is a minor leak" comment exists for something that scales with a variable the codebase doesn't control (how many times a human reloads a script during a session), re-derive the actual bound rather than trusting the old estimate.

## Round 8: `shutdown()` didn't actually wait for the old thread to die, and `/reload` itself was silently undoing Round 7's registry

**Symptom, reported live**: "we end up running out of GPU memory as we save and the components reload their extensions" -- despite Round 7's registry-based fix already being deployed and, on the surface, working (thread count staying flat across a reload). Confirmed the trigger directly: saving the project causes TD's own file-sync to notice a Callbacks DAT's backing `.py` file and re-execute its module (this is TD's own behavior, not something this project's code controls) -- a live before/after snapshot of `_manager_registry` across one real `/save` call caught exactly one manager (`YOLO26_POSE`) getting a fresh `id()`, i.e. a genuine reconstruction triggered purely by saving.

**Root cause #1 -- `shutdown()` was fire-and-forget, not a real handoff.** It sent the worker thread its shutdown sentinel and returned immediately, without confirming the thread had actually exited. The calling script's "Create global instance" section proceeds straight into constructing and loading the NEW model the instant `shutdown()` returns -- meaning the OLD model's CUDA session and the NEW model's CUDA session can both be resident in GPU memory at once for however long the old thread takes to actually unblock and return (longer if it was mid-inference when the sentinel arrived). On a GPU already sitting at 80%+ steady-state across 5-8 loaded models (this project's normal load), that transient overlap during exactly a save-triggered reload is what tips it into running out of memory -- not a permanent per-reload leak, but a real spike at the worst possible moment.

**Root cause #2 -- this project runs with cyclic GC globally disabled** (see the module-level `gc.disable()` comment near the top of `onnx_inference_manager.py` -- a deliberate, separately-measured fix for multi-second TD freezes during real-time inference, unrelated to this bug but directly relevant to it). With cyclic GC off, ANY reference cycle in a shut-down manager's object graph sits uncollected for the life of the process; plain refcounting alone has to resolve everything. CPython's own `threading.Thread._bootstrap_inner` clears `self._target` once the thread function returns, which normally breaks the obvious `self -> _worker_thread -> _target -> self` cycle via refcounting alone with no cyclic GC needed -- but that cleanup only happens once the thread has genuinely finished, which `shutdown()` wasn't waiting for.

**Fix**: `shutdown()` now calls `self._worker_thread.join(timeout=5.0)` right after sending the sentinel, so it only returns once the old thread has actually exited (logging a warning and proceeding anyway if a stuck inference call blows the timeout, rather than hanging forever) -- then calls one manual `gc.collect()` as cheap insurance against any other cycle this class doesn't yet know about. This does NOT re-enable the periodic/automatic collector Round 2's freeze-fix disabled; it's a single, deliberately-scheduled sweep at a moment that is provably NOT mid-inference (between one model's teardown and the next model's load), which is exactly the safe lever that `gc.disable()`'s own comment predicted would be needed if slow growth were ever observed.

**Root cause #3, found while investigating #1/#2 -- `/reload` was quietly defeating Round 7's own fix.** `_manager_registry = {}` was a plain module-level reassignment; `importlib.reload()` (what `/reload` calls under the hood) re-executes a module's top-level code against its EXISTING `globals()` dict, not a fresh namespace -- so every `/reload` call wiped the registry back to empty, silently orphaning every currently-tracked instance (still alive and running fine, just no longer tracked). Confirmed live: this happened twice in one session purely from calling `/reload` for unrelated reasons (picking up changes to a different shared module). Any of those orphaned comps' NEXT reconstruction would find nothing in the registry to shut down, quietly re-enabling the exact leak this whole mechanism exists to prevent, for the rest of that TD session. Fixed with the standard reload-safe-module-state idiom: `if '_manager_registry' not in globals(): _manager_registry = {}` -- since reload() reuses the same `globals()`, the guard now preserves the existing dict across any future `/reload` instead of discarding it. Confirmed live: a real `/reload` before and after this fix left every registered instance's `id()` unchanged.

**Verification**: snapshotted `nvidia-smi`'s `memory.used` immediately before and after a real `/save` with both fixes deployed -- 13121 MiB before, 13135 MiB after (effectively flat, no double-load spike), zero errors on any comp.

**Takeaway:** a fix that's correct in isolation (Round 7's registry) can still be undone by a DIFFERENT, unrelated maintenance action (calling `/reload` for a totally separate reason) if the fix's own persistence mechanism doesn't account for that action's specific semantics (here: does re-execution get a fresh namespace, or the same one?) -- don't just verify a fix once; re-verify it survives every OTHER routine operation that touches the same module.

## Round 9: `onnx_movenet.py` "a frame behind" the legacy `MovenetONNX.py` -- one real bug found and fixed, one real timing gap still open, and one comparison methodology trap that explained more than either

**Symptom, reported live**: comparing the new ByteTracker/KeypointTracker-based `onnx_movenet.py` (a Script TOP) side by side against the legacy `tox/haxlib/ml/onnx/MovenetONNX.py` (a COMP extension driving a Script CHOP, `CookLevel.ALWAYS`) at the identical model and resolution, the old one looked consistently a frame or so ahead.

**Real bug #1 (fixed, see also the earlier fix in this same session before this Round was written up): `onCook`'s early `return` after consuming a completed result.** The base class's own docstring already claimed a "MoveNet-inspired" threading model (consume a result and dispatch the next capture in the same call), but an unconditional `return` right after `copyNumpyArray()` meant the next capture always waited for a whole separate cook cycle -- one full extra frame of latency, every single cycle, for every script using this base class. Fixed by deleting that `return` so execution falls through to the capture/dispatch code below in the same cook, matching the old script's `runInferenceThreaded()` (which does exactly this: consume `pending_keypoints`, then immediately check `is_inferencing` and dispatch a fresh capture, same call).

**Investigated and RULED OUT, each via direct live A/B measurement, not reasoning alone** (temporarily instrumenting both the old extension's `runInferenceThreaded` and the new manager's `onCook`/`get_session_options` via safe, reversible monkey-patches -- restored after each test):
- **Working resolution** -- both are 384x320 (an earlier network inspection was stale; the user had already matched them).
- **Smoothing amount** -- old's `Lerpamp` and new's `Outputsmoothing` are both 0.5.
- **`copyNumpyArray`'s mandatory per-cook GPU texture upload** (a cost the old Script-CHOP-based design never pays at all, since CHOPs carry no pixel data) -- A/B tested with a temporary `skip_copy_for_diagnostic` toggle in the base class; completion-rate ratio barely moved (1.158 -> 1.168 old/new). Removed the toggle once ruled out -- don't leave temporary diagnostic branches in shared code after the question they existed to answer is settled.
- **Explicit `SessionOptions`** (`ORT_ENABLE_ALL`/`ORT_SEQUENTIAL`) that the base class sets and the old script never did -- tested via a temporary `get_session_options()` override returning `None` (matching old exactly); no improvement (17.1ms vs 15.6ms, within noise).
- **Cross-model GPU contention** -- checked directly; every other `ONNX_Playground` comp was already cooking-disabled during all of these measurements, so this was never a factor.

**Gotcha hit while testing the `copyNumpyArray` hypothesis**: tried to monkey-patch `scriptOp.copyNumpyArray` itself to a no-op for a measurement window -- `AttributeError: 'td.scriptTOP' object attribute 'copyNumpyArray' is read-only`. TD's C++-backed OP methods aren't freely reassignable like plain Python object attributes; the safe pattern is to add a plain Python-level toggle to YOUR OWN code (a real instance attribute on the manager, checked before calling the read-only method) rather than trying to patch the method itself. The failed patch also left the live comp erroring until manually restored (`del`-ing the half-applied wrapper's saved-original references) -- a reminder that even "safe, reversible" live monkey-patching needs its OWN error handling, since a broken patch can outlive the /run call that installed it.

**Still-open, real, and NOT explained by anything above**: at the identical 384x320 resolution, old's raw `session.run()` consistently measures ~5-9ms while new measures ~13-17ms -- a genuine 1.6-2.5x gap in the inference call itself. Remaining untested candidates: pre-allocated/reused input buffer (new) vs a fresh `.astype(int32)` array every call (old) interacting differently with the CUDA EP's memory handling; something else specific to how each constructs/binds the input tensor. Not yet root-caused -- pick this up before concluding anything further about relative performance between the two implementations.

**The methodology trap that explained the ORIGINAL "frame behind" report better than any of the above**: the user's live comparison technique was to PAUSE the project and watch each implementation's smoothed keypoints settle. `MovenetONNX.py` has **zero pause-awareness** -- no `time.play` check anywhere -- so it keeps capturing, inferring, and lerp-smoothing the same static frame every single real frame for as long as the project stays paused, continuing to converge/drift indefinitely. The new base class deliberately freezes the instant `scriptOp.time.play` goes false (matching every other script in this project, to avoid burning GPU/CPU on a paused scene). Comparing the two AFTER pausing will always show a mismatch -- confidence scores, settled position, everything -- because one side is still working and the other correctly stopped. This is not a bug in either; it's an invalid comparison methodology. Confirmed by grepping the old script for any pause-related check at all (zero matches) and cross-checking the base class's own `if not scriptOp.time.play: return` line. Decision: leave the new behavior as-is (it's the deliberate, correct design) rather than replicate the old script's always-on-while-paused behavior -- re-run any future comparison on live moving footage, not a paused frame.

**Takeaway:** when two implementations disagree under a specific test condition (here: paused), check whether BOTH implementations even attempt to do the same thing under that condition before hunting for a performance/threading bug -- a silent behavioral difference in how "paused" is handled produced a more confusing, misleading signal than any of the real (and separately real) timing differences underneath it.

**Follow-up, same investigation: added `ONNXInferenceManager.on_result_published()`**, a new overridable hook called from `onCook()` immediately after `copyNumpyArray()` publishes this frame's texture, and BEFORE the fall-through capture/dispatch of the next frame (see Root cause #1 above). Existing scripts' `pending_table_update`-flag-checked-by-the-wrapper-after-onCook-returns pattern still works (nothing broke), but it publishes its Table DATs one full "capture the next frame" operation later than it needs to, every single cook -- purely from CPU-time ordering, not a data bug (see the "ORDERING NOTE" comment in `onCook()`). `on_result_published()` lets a subclass flush those outputs at the earliest possible point in the same cook instead, matching how `tox/haxlib/ml/onnx/MovenetONNX.py`'s `OutputSkeletonsToChop()` always worked (called immediately after consuming a result, same call, never after dispatching the next one). Migrated `onnx_movenet.py` to it as the first adopter; every other tracker script still uses the older flag pattern and is unaffected, migrate opportunistically rather than in one sweep. Thread-safety: identical to `postprocess()`'s -- `on_result_published()` only ever runs on the main thread (called synchronously from `onCook()`), so moving table writes earlier introduces no new cross-thread access.

**Follow-up #2: confirmed old and new can legitimately be looking at DIFFERENT real frames at any given instant, by design.** Both pipelines call `numpyArray(delayed=True)` independently, on their own cook's own schedule, with zero synchronization between the two comps -- there is no shared frame-lock. Combined with old's measurably higher completion rate (Round 9's ~13-16% gap), old is less often mid-inference when a new frame arrives, so it drops fewer real frames than new -- directly answering "does old have a better chance of picking up each frame": yes, confirmed, and it's the same root cause as the original "smoother without any lerping" report, not a separate mystery. A larger gap between successfully-processed frames is inherently choppier than a smaller one, with or without smoothing.

**Follow-up #3, ruled out**: raw pixel value range/format as a source of the ever-present confidence mismatch. Checked live: both `fit_square_sm1` (new) and `null_input` (old) report `pixelFormatName='rgba8fixed'` and an identical `numpyArray()` range (`float32`, min 0.0 / max 1.0). `numpy_util.denormalize_td_image()`'s defensive `if nA.max() <= 1.0` check (which old's preprocessing pipeline calls and new's doesn't) is a no-op for this specific pixel format -- not the source of the confidence discrepancy after all, though it remains a reasonable defensive check for a TOP chain that might use a different (e.g. floating-point/HDR) pixel format elsewhere.

**Follow-up #4, tested, inconclusive**: cached `session.get_inputs()[0].name`/explicit single-output-name list (matching old's exact `session.run([output_name], {input_name: tensor})` call shape) instead of the base class default's per-call name lookup and `output_names=None`. Measured 10.9-15.2ms across several samples post-change vs. 13-17ms pre-change -- overlapping ranges, no clear win. Kept in `onnx_movenet.py`'s `run_inference()` override anyway (strictly no worse, marginally cheaper per call), but this is NOT the explanation for the raw inference-time gap. That gap remains genuinely open -- candidates not yet tested: input buffer reuse (new's pre-allocated buffer written in-place every call) vs. a fresh allocation each call (old); something else specific to how each constructs the actual tensor object handed to `session.run()`. Whoever picks this up next should take averaged samples over 50+ calls, not single readings -- per-call jitter in this range (roughly +/-5ms) is large enough to make single-sample A/B comparisons unreliable, as happened during this round's own testing.

## Round 10: cold-start bootstrap without an Execute DAT, `opPerformance` removal, and finally explaining why `Framedelay=2` is correct

**Symptom, reported live**: `YOLO26_SEG`'s `script1` never cooked (and its ONNX model never loaded) after a fresh TD app start unless someone manually visited the network in the editor. Root cause: `onGetCookLevel` already returns `CookLevel.ALWAYS`, but per TD's own cook-request/cook-reason split, `ALWAYS` only sustains cooking once a request already exists -- nothing in this network wires `YOLO26_SEG`'s output downstream to anything actually rendered, so nothing ever gives `script1` its first request. Opening the network in the editor activates the OP tile's viewer, which is the first real request; after that it self-sustains.

**First attempt: a dedicated `execute_prewarm_model` Execute DAT** (Frame Start, unconditional every frame regardless of cook state) force-cooking `script1` only while `needs_prewarm()` (a new `ONNXInferenceManager` method: `self.session is None and self.load_error is None`) was true, then stopping once loaded -- avoids running real inference forever on an unselected effect, unlike a naive "always force-cook" version. Worked, verified live on an actual cold TD restart (confirmed via `webServerTotalCooks` on a fresh bridge connection, zero prior network visits).

**Bug caught along the way, unrelated to the cook-loop logic itself: `td_http_api.py`'s `/dat` POST route never decoded `request['data']` from `bytes` before assigning it to `DAT.text`.** TD's Web Server DAT callback hands POST bodies over as raw `bytes`; assigning bytes directly to `.text` doesn't auto-decode, it just stringifies the object -- every `/dat` POST during this investigation had silently written the literal text `b'"""\nExecute DAT\n...'` (one line, no real newlines) into the target DAT instead of the actual script, which TD then correctly reported as `Cannot find function named: onFrameStart` (a genuinely useful error, once actually read) rather than a compile error. **Fix**: decode `bytes`/`bytearray` to `str` before the `.text`/`.csv` assignment. This silently broke every `/dat` POST made before the fix was found, not just this one -- worth re-checking after the fact if any earlier `/dat` push in a session predates catching this.

**Second attempt, at the user's request: replace the Execute DAT with pure Python, so the trigger lives in the same file as the model-loading code it kicks off.** First draft called `op('script1').cook(force=True)` directly from `onnx_yolo26_seg.py`'s own module-level bootstrap code -- and TD rejected it outright: `"Unexpected error during compilation... check for cook loop or recursive module dependencies."` Root cause: this file IS `script1`'s own Callbacks DAT, compiled as part of `script1` itself cooking -- a synchronous `cook()` call on the same node mid-compile is a real reentrant-cook violation, not a style nitpick. **Fix**: defer via `td.run(script_string, delayFrames=1)` instead of a direct call -- runs one frame later, outside the current compile's call stack. `ONNXInferenceManager.schedule_prewarm_cook(scriptOp, callbacksDAT)` only ever calls `td.run()`, never `.cook()` directly, so it's safe to call from anywhere including this exact reentrant context; the actual `scriptOp.cook(force=True)` + reschedule lives in a separate `_prewarm_tick()`, only ever invoked via that deferred call. Also worth knowing: this module does `import td` explicitly specifically because it's a plain Python-imported file (not a directly-executed DAT script), so TD's usual pre-loaded globals (`run`, `op`, ...) aren't automatically in its namespace -- has to be `td.run()`, not a bare `run()`, which is an easy, silent `NameError` to introduce when moving code that assumed DAT-script-global conventions into a plain imported module.

**Considered and explicitly rejected: resolving `scriptOp` structurally (searching siblings for whichever `scriptTOP`'s `par.callbacks` points back at this exact DAT) instead of a literal `op('script1')` string.** Implemented and verified live (correctly found `script1` via the real `par.callbacks` relationship, zero hardcoded names), but reverted at the user's explicit preference for a plain, explicit `op('script1')` reference -- matching the existing `opPerformance = op('constant_performance')` convention already used one line above it in the same file. **Takeaway: a more "structurally correct" solution isn't automatically the right one to ship if it trades a simple, obviously-correct one-liner for a new method's worth of indirection just to avoid a literal name that was never actually ambiguous in the first place** -- the callbacks DAT and its Script TOP are already a fixed 1:1 pair by construction in this project's conventions.

**`self.opPerformance` (an external `constant_performance` CHOP reference, set per-script and written to from `onCook`) was removed entirely** -- confirmed unused this session, across the shared base class and all 11 `onnx_*.py` scripts (the unrelated `tox/haxlib/ml/onnx/MovenetONNX.py`'s own `self.opPerformanceChop` was explicitly left alone -- different mechanism, different file, not part of this cleanup).

### Auto-driving `Framedelay` from measured latency: implemented, tested live, reverted -- the cache mechanism can't tolerate a changing value

Added `_update_sync_estimate()`: a rolling-window (1s), few-times-a-second (0.2s) smoothed estimate of `last_pipeline_frames`, using an asymmetric response (jump UP immediately to the window's max -- under-delaying is a real correctness bug, the cache/cacheselect compensator would read a not-yet-ready or stale frame -- but ease DOWN by at most one frame per tick, so a brief spike can't cause lasting overcorrection or flicker). Written to the existing `Pipelineframes` read-only par (replacing the old raw single-frame number, too noisy to read at a glance), and, gated behind a new opt-in `Autoframedelay` toggle (default off), to the network's own pre-existing `Framedelay` custom par.

**The user tried `Autoframedelay` live and found it measurably worse than the static, manually-tuned `Framedelay=2`** -- confirmed mechanically, not just anecdotally: `cache1`'s `cachesize` expression and `cacheselect1`'s `index` expression are BOTH driven directly off `Framedelay`, so changing it doesn't just adjust a number, it resizes the cache AND jumps the read index to a different point in the buffer -- a visible skip/rewind in the delayed passthrough video every single time it changes, regardless of whether the new value is "more correct." With `Pipelineframes` genuinely oscillating 4-5 within a one-second window, auto-driving `Framedelay` from that glitches often enough to look worse than a fixed, slightly-imperfect value that never glitches at all. **Takeaway: a signal being "more accurate on average" doesn't make it safe to auto-apply, if the thing consuming it can't tolerate the signal's own noise -- check whether the actuator is glitch-tolerant BEFORE building the automation, not after a live A/B shows it's worse.** `Autoframedelay` stays in the codebase (off by default, opt-in), but isn't recommended for this particular cache/cacheselect Framedelay mechanism.

### Two failed ground-truth latency measurement attempts, and what finally explained `Framedelay=2` without needing either

Tried to settle whether `Pipelineframes`' 4-5 reading was a real recurring stall or a measurement artifact, by cross-correlating the tracker's own reported position against an independent, non-ML motion signal computed directly from the raw input texture (frame-differencing, no model involved) -- fully automated, no human-performed test needed.

- **Attempt 1 (whole-frame motion centroid)**: weak, inconclusive result -- best correlation only 0.405, and a smooth near-monotonic ramp across candidate shifts rather than a sharp peak (the signature of noise, not a real measurement). Root cause: `people_walking` usually has multiple people in view simultaneously; averaging the position of ALL moving pixels in the frame together dilutes/mixes every walker's motion into one signal, while `tracked_objects[0]` is one SPECIFIC person's track -- the two were never going to correlate well regardless of the true delay.
- **Attempt 2 (single-blob restriction)**: refined to isolate connected motion blobs (`scipy.ndimage.label`) and only sample when exactly one clear blob AND exactly one tracked person existed simultaneously -- zero samples in ~25 seconds of real footage. Either multiple people are in view almost always in this source video, or (more likely, based on how frame-differencing typically behaves) a single walking person's own silhouette fragments into several disconnected motion regions frame-to-frame (limbs moving independently, torso relatively static) rather than one contiguous blob, so "exactly one blob" essentially never triggers even for a genuinely solo walker.

Both probes were built as temporary, `_`-prefixed Execute DATs (Frame Start, unconditional per-frame sampling into module-level lists) and destroyed immediately after each analysis, per this project's probe-hygiene convention -- confirmed zero residue left in the live network either time.

**What actually explained `Framedelay=2`, once the new per-stage diagnostics (below) existed to check it against: plain arithmetic on the ALREADY-MEASURED rolling averages.** `Inferencems` (~11.7ms, worker thread) is comfortably under one frame (16.67ms @ 60fps) -- confirmed by `Frameskippedpct: 0.0`, meaning the worker thread's result is never late when the next cook checks for it, so capture-on-frame-N -> consume-on-frame-N+1 is a clean 1-frame async handoff. But `Postprocessms` (~16.2ms) + `Preprocessms` (~2ms) both run as BLOCKING main-thread work within that SAME consuming cook call -- roughly 18ms total, slightly OVER one frame's budget, pushing that cook call's own real-world duration past a second full frame period. Sum: ~1 frame (async handoff) + ~1.1 frames (main-thread overrun) ≈ 2 frames, matching the empirically-tuned `Framedelay=2` almost exactly.

**This also reconciles the "4-5 vs 2" discrepancy that motivated the whole ground-truth chase, without needing either failed probe at all**: `Preprocessms`/`Inferencems`/`Postprocessms` are rolling AVERAGES (typical case); `Pipelineframes` is a rolling MAX over the same window (worst case, by design -- see above). Both can be true simultaneously: the TYPICAL cycle really does cost ~2 frames (matching what looks visually correct nearly all the time), while rarer spikes (more people in frame driving up postprocess cost, momentary GPU contention) push the MAX to 4-5 -- brief and infrequent enough that the pipeline's own existing temporal smoothing (box EMA, held mask state across missed detections) masks them before they'd ever be visually noticed. Not a measurement bug -- two different, both-correct statistics of the same underlying noisy process, being read as if they were meant to agree.

### New shared diagnostics added to `ONNXInferenceManager` (every subclass gets these for free)

Three new read-only custom pars, joining the existing `Effectivefps`/`Pipelineframes`: **`Preprocessms`**, **`Inferencems`**, **`Postprocessms`** -- rolling AVERAGES (not max; pure diagnostics, nothing downstream depends on them the way `Framedelay` depends on `Pipelineframes`, so a representative typical cost is more useful than deliberately surfacing a worst-case spike) of the already-computed `last_preprocess_ms`/`last_inference_ms`/`last_postprocess_ms`, same rolling-window/update-cadence machinery as `_update_sync_estimate()`, factored into a shared `_rolling_average()` helper. Plus **`Frameskippedpct`**: rolling-average percentage of `frames_skipped_final` relative to each completed cycle's total length -- how much of the pipeline's own cadence goes to waiting on a still-busy worker thread, distinct from `Effectivefps` (compute time only, blind to skipped/wasted cook calls).

**Rule of Thumb (Round 10):** when a signal used to drive an automatic correction turns out noisier than the mechanism it's correcting can tolerate, that's a real finding about the ACTUATOR, not just the signal -- fix by checking glitch-tolerance before automating, not by trying to smooth the signal harder. And when two metrics about "the same thing" seem to disagree, check whether they're actually measuring different STATISTICS (average vs. max, typical vs. worst-case) of the same underlying process before assuming either one is wrong.

## Round 11: disabling cyclic GC globally, to fix periodic multi-second freezes (predates the Round numbering above, documented retroactively)

**Symptom**: TD would periodically freeze for ~2 seconds every 5-10 seconds during real-time ONNX inference, fully recovering afterward. Looked at first like a GPU/CUDA stall.

**Root cause, confirmed with a `/run`-script diagnostic wrapping `run_inference()` and recording per-call timing over hundreds of samples**: disabling Python's cyclic garbage collector (`gc.disable()`) made the freezes disappear completely -- 0 outliers over 45s / ~700 calls, vs. 4 near-identical ~2075ms outliers in the previous 45s window with GC enabled. A live TD project has an enormous number of long-lived Python-wrapped OP/Par objects for the cyclic collector to traverse on every full (gen2) collection pass -- expensive purely from graph *size*, not from actual garbage volume (`gc.get_stats()` showed only dozens of objects actually collected per gen2 pass). This is a known class of problem in real-time Python hosts generally (long-lived object graph + periodic stop-the-world tracing), not specific to this project's own code.

**Fix**: `gc.disable()` once, at import time, in `onnx_inference_manager.py` -- a process-wide change (affects every Python script/extension in the TD session, not just ONNX scripts), so it's placed in the shared base class rather than per-script. Reference-counting (Python's primary memory management, always active regardless of this setting) still immediately frees the overwhelming majority of objects -- this only stops *cycle* detection. Real but usually small tradeoff: any code elsewhere in the project that creates a true reference cycle (e.g. an extension holding a back-reference to its owner COMP) leaks that cycle's memory for the life of the process instead of having it swept up periodically. Judged acceptable given the alternative is a multi-second UI freeze every few seconds during any real-time inference.

**If a slow memory growth is ever observed over very long (hours+) sessions**, the next lever is an explicit periodic `gc.collect()` scheduled at a deliberately-idle moment (not mid-inference) -- not re-enabling automatic collection. This is exactly the lever Round 7/8 reached for later, once a real reference-cycle leak (the abandoned worker-thread/manager-instance cycle) was found and needed a manual, precisely-timed collection pass rather than the periodic collector this round disabled.

**Rule of Thumb (Round 11):** a periodic multi-second freeze that looks like a GPU/CUDA stall is worth ruling out Python's own cyclic GC for, in any long-running real-time host with a large, long-lived object graph -- the cost scales with graph size, not garbage volume, so it can look identical to an unrelated external stall until measured directly.

## Round 12: `CookLevel.AUTOMATIC` can permanently stop a script from cooking, with no way to self-recover

Surfaced independently by two separate comment-cleanup passes over `onnx_yolo26_seg.py` and `onnx_yolo26_obj_det.py`'s `onGetCookLevel()` docstrings -- both scripts already carried this reasoning inline (not previously written up centrally), and both landed on the same finding.

**The problem**: every `onnx_*.py` script's `onGetCookLevel()` returns `CookLevel.ALWAYS` unconditionally, never `CookLevel.AUTOMATIC` (TD's own default, "inputs changed and output being used"). The reason: this project's consumers of a script's tracked results (`tracked_objects`) read it via a raw Python module reference (`op('...').module.inference_manager.tracked_objects`, the same pattern this skill doc's own Round 10 cold-start work and other tooling uses), not a wire or parameter reference. TD's own "is the output being used" dependency check has no visibility into a plain Python attribute read like that -- it only tracks wires and parameter expressions. Under `AUTOMATIC`, if TD ever concludes the output isn't being used by anything it can see, it stops cooking the node.

**Why that's permanent, not transient**: `CookLevel` is only reconsidered when TD already has an active cook request pending for that node -- it's an answer to "given that something wants this to cook, what's its reason to do so," not a mechanism that itself generates requests (see Round 10's cold-start work for the fuller version of this same request-vs-reason distinction). Once `AUTOMATIC` settles into "not cooking," nothing external prompts TD to re-check later. Confirmed live: resuming play after a pause does NOT nudge it back, because play/pause isn't a registered dependency of the op either -- the node just stays permanently stopped until something else (reopening the network, an explicit force-cook) gives it a fresh request from scratch.

**Fix**: return `CookLevel.ALWAYS` unconditionally instead. Once *any* mechanism gives the node its first cook request (a viewer, `schedule_prewarm_cook()` from Round 10, etc.), `ALWAYS` guarantees every subsequent frame re-cooks regardless of whether TD can see a "real" consumer -- sidestepping the whole "is my consumer visible to TD's dependency graph" question entirely. The actual pause-awareness this project still wants (don't burn GPU/CPU on a paused scene) is handled separately, inside `onCook()` itself (`if not scriptOp.time.play: return`), which correctly re-triggers the instant play resumes since it's a plain per-cook check, not a `CookLevel` decision.

**Rule of Thumb (Round 12):** if anything downstream of a node consumes its data via a raw Python/module reference rather than a wire or parameter expression, `CookLevel.AUTOMATIC` cannot see that consumer and may stop cooking the node permanently, with no built-in way to notice and recover. Default to `CookLevel.ALWAYS` for any node whose real consumers include Python-reference reads, and put actual idle/pause optimization in the cook body itself, not in `onGetCookLevel()`.
