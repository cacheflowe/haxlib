# ONNX Runtime in TouchDesigner

## CUDA EP silently falls back to CPU: cuDNN 9.24 breaks conv engine selection in onnxruntime-gpu 1.22.0

**Symptom:** Model loads fine, logs show `CUDAExecutionProvider` active, but the very first
`Conv` node throws and ORT silently falls back to CPU:

```
EP Error: [ONNXRuntimeError] : 11 : EP_FAIL : Non-zero status code returned while running Conv node.
Name:'/model.0/conv/Conv' Status Message: Failed to initialize CUDNN Frontend
...cudnn_fe_call.cc:99... CUDNN_FE failure 11: CUDNN_BACKEND_API_FAILED ...
expr=s_.cudnn_fe_graph->build_operation_graph(handle);
Falling back to ['CPUExecutionProvider'] and retrying.
```

Inference still "works" (correct output) but silently runs on CPU, which tanks framerate —
easy to miss since there's no hard crash.

**Root cause:** `onnxruntime-gpu` (since ~1.20) uses the cuDNN Frontend API for Conv, which
picks a GPU "engine" per conv shape/dtype/GPU. Certain cuDNN 9.x point releases regress engine
selection for otherwise-ordinary convs (plain 3x3 stride-2, symmetric padding) on some GPUs.
Confirmed as a known upstream issue by an ORT maintainer:
[microsoft/onnxruntime#23301](https://github.com/microsoft/onnxruntime/issues/23301),
[#26274](https://github.com/microsoft/onnxruntime/issues/26274).

This project's venv had resolved the newest `nvidia-cudnn-cu12` (`9.24.0.43`) because neither
`onnxruntime-gpu[cuda,cudnn]==1.22.0` nor a bare pip install pins the cudnn sub-version — pip
just grabs latest at install time. A sibling project (`touchdesigner-onnx`) created its venv
earlier and had `nvidia-cudnn-cu12==9.11.0.98`, which works fine with the same
`onnxruntime-gpu==1.22.0`.

**Fix:** Pin cuDNN explicitly instead of leaving it to float:

```
onnxruntime-gpu[cuda,cudnn]==1.22.0
nvidia-cudnn-cu12==9.11.0.98
```

Then reinstall in the venv and restart TouchDesigner (so it relaunches with the updated DLLs):

```powershell
& ".venv/Scripts/python.exe" -m pip install "nvidia-cudnn-cu12==9.11.0.98"
```

**How to debug this class of error in general:**
1. Compare the exact `nvidia-cudnn-cu12` / `onnxruntime-gpu` versions between a known-working
   project and the broken one — check `Lib/site-packages/*.dist-info` folder names directly if
   the other venv's Python interpreter no longer exists (e.g. after a TD upgrade moved its bin
   path), rather than relying on `pip list` needing a live interpreter.
2. `onnxruntime-gpu==1.19.x` predates the mandatory cudnn-frontend path for Conv and is a
   fallback option if pinning cudnn doesn't help.
3. Don't assume the CUDA EP is actually running just because it's listed in
   `session.get_providers()` at load time — ORT's automatic CPU fallback on a failed node is
   silent per-inference, not a session-level failure.

See also: [.ai/skills/td-ml.md](../../.ai/skills/td-ml.md) for ONNX Runtime setup guidance.

## `arena_extend_strategy='kSameAsRequested'` regressed CUDA EP performance despite sound-sounding reasoning

**Symptom:** After adding explicit CUDA EP options to `onnx_util.providers()` (`device_id` + `arena_extend_strategy='kSameAsRequested'`) alongside an unrelated persistent-worker-thread refactor, a live network's effective FPS dropped from the ~80s to the mid-50s, and its cache/cacheselect `Framedelay` needed to *increase* by 2 frames to stay visually synced — the opposite of the intended effect.

**Root cause:** The reasoning going in was: "every script here runs a fixed input shape every frame, so ORT's default doubling-growth arena (`kNextPowerOfTwo`) buys nothing, and `kSameAsRequested` should reach a steady allocation just as fast." That reasoning was never measured in isolation before shipping. In practice, `arena_extend_strategy` controls how the CUDA memory arena **grows** when it needs *more* memory than it currently has cached — not whether it reuses memory at all. If a model's actual internal allocation pattern isn't byte-identical on every single call (likely for most real models, even with a fixed input shape), `kSameAsRequested` forces the arena to re-extend — a real, synchronizing `cudaMalloc` — far more often than the default, which rounds generously and rarely needs to re-extend at all.

**Fix:** Reverted `arena_extend_strategy` entirely (kept `device_id`, which was harmless). Re-measured live: effective FPS recovered to ~89-96, better than the pre-change baseline (the persistent-worker-thread change was a genuine, separate win that had been masked by this regression riding along with it).

**How to debug this class of error in general:**
1. Never adopt an ORT/CUDA tuning knob from documentation-reading or "sounds right" reasoning alone — A/B it with a live measurement before keeping it. This project already had a fast, cheap way to do that (`Effectivefps`, a self-installing read-only custom par — see [.ai/skills/td-threaded-inference-optimization.md](../../.ai/skills/td-threaded-inference-optimization.md)), and skipping that step here is exactly what let a plausible-sounding but wrong change ship.
2. When two changes land together (here: a genuine win + a regression), isolate them one at a time rather than reading the combined result as one verdict — the combined effect can hide a real improvement inside a net-negative number.
3. See [.ai/skills/td-threaded-inference-optimization.md](../../.ai/skills/td-threaded-inference-optimization.md)'s "Round 2" section for the fuller story, including a second, subtler lesson from the same investigation: a latency metric that only measures processing time after data receipt can't detect a change in how *stale* that data was, which cost an extra round of back-and-forth before a real 6→3 frame latency win (`numpy_array_delayed=False`) was correctly recognized as a win instead of reverted as a regression.

## Batching a variable number of items into one `session.run()` call re-triggers CUDA's per-shape algorithm search

**Symptom:** `onnx_hsemotion.py` runs a second model (emotion classification) once per currently-tracked face — a count that varies frame to frame. Replacing the naive "one `session.run()` call per face" loop with the seemingly obvious optimization — stack all N face crops into one batched call — made `postprocess()` spike to 650-670ms on every frame that classified, roughly **35x slower** than the ~19ms the naive per-face loop took for the same 5 faces.

**Root cause:** Confirmed with a standalone timing sweep (call the same session repeatedly with `N = 1, 2, 3, 4, 5, 6, 8, 10, 12, 4, 5, 10, 3, 7, 9`, printing each call's wall time): the *first* call at any given `N` took 3.6-5.7 **seconds**; a *repeat* call at an already-seen `N` took ~10ms. ONNX Runtime's CUDA EP performs a one-time cuDNN convolution-algorithm search the first time it sees a given input shape, then caches that choice for later calls with the *same* shape. The original per-face loop never noticed this because every call was always shape `(1, 3, 260, 260)` — the cache warmed up once, ever. Batching by the real (varying) face count meant the batch dimension changed almost every frame, so nearly every classification frame hit a brand-new shape and re-paid the multi-second search from scratch.

**Fix:** Pad every batched call to one fixed ceiling size (`MAX_BATCH_FACES = 16`) with zero-filled dummy crops, so the shape passed to `session.run()` never varies regardless of the real face count; only read back the first N (real) results. Confirmed live: effective fps went from ~38 (naive per-face) to a broken multi-second-stutter version (naive batching) to ~58-60 (fixed-size padded batching) — a genuine win once the shape-stability trap was closed.

**How to debug this class of error in general:**
1. Before trusting that "batch N items into one call is faster than N separate calls," check whether N is fixed or varies at runtime. If it varies, verify with a standalone timing sweep across several different N values (repeating a few) *before* deploying — this is the second time in this project's history that an ORT CUDA-EP-level "caches something per exact shape" behavior has silently ambushed an otherwise-reasonable-sounding optimization (see this file's `arena_extend_strategy` entry above for the first).
2. This is the same underlying ONNX Runtime behavior as the recurrent-state resolution-change issue documented in [.ai/skills/td-threaded-inference-optimization.md](../../.ai/skills/td-threaded-inference-optimization.md)'s "Round 4" (RVM's `io_binding` needing recreation on a large `Inputwidth` change) — one is about output-buffer shape, this one is about convolution-kernel selection, but both are the CUDA EP caching expensive setup work per exact input shape, paying a real first-time cost on any shape it hasn't seen before, not just once at model load.
3. See [.ai/skills/td-threaded-inference-optimization.md](../../.ai/skills/td-threaded-inference-optimization.md)'s "Round 5" for the fuller story, including `cudnn_conv_algo_search: 'HEURISTIC'` as an untested alternative/complementary lever.
