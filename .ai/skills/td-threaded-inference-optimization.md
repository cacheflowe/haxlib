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
