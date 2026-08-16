"""
ONNXInferenceManager - Base class for TouchDesigner ONNX model inference with threading

This class encapsulates all the common patterns for loading and running ONNX models
in TouchDesigner with threaded inference to avoid blocking the main render loop.

Usage:
    Create a subclass and implement:
    - get_model_path(): Return the path to your ONNX model
    - preprocess(nA): Transform input numpy array to model input tensor
    - postprocess(outputs): Transform model outputs to final numpy array
    
    Optional overrides:
    - get_session_options(): Customize ONNX session options
    - on_model_loaded(session): Called after model loads successfully
"""

import os
import time
import math
import threading
import queue
import gc
import numpy as np
import onnxruntime as ort
# `td` is the one TD global this module imports explicitly (against the usual DAT-script
# convention of never importing it) -- absTime/op/parent/etc. are "pre-loaded globals" for
# a DAT's own directly-executed script code, but this is a plain imported module
# (python/util/), and that injection doesn't reliably reach here (confirmed live: worked
# during one dev session, then broke every ONNX script after a clean TD/machine restart).
# `import td` gives a real, stable module reference regardless of execution context.
import td

# Import util modules (will be available in TouchDesigner context)
import numpy_util as npu  # numpy utilities

# ========== ONNX logging/provider helpers ==========
# Every onnx_*.py script calls check_providers via the self.check_providers() instance
# method below, and providers()/log_onnx_options()/log_model_details() as plain module-
# level functions (see _load_model_thread() and any script that loads its own secondary
# session, e.g. onnx_hsemotion.py's emotion classifier). tox/haxlib/ml/onnx/MovenetONNX.py
# is the one exception -- it looks 'onnx_util' up via TD's DAT-based mod() mechanism
# instead of a plain import, and is intentionally NOT migrated to this pattern: it
# predates ONNXInferenceManager entirely and is kept as a frozen comparison baseline.

def printONNX(*args):
	print("[ONNX]", *args)

def log_onnx_options():
	printONNX('version', ort.__version__)

def providers(gpu_mem_limit_bytes=None):
	"""CUDA (falling back to CPU) execution provider list, with explicit CUDA EP options.

	Do NOT set arena_extend_strategy='kSameAsRequested' -- measured as a real regression
	(rf-detr-seg-nano.onnx: ~80fps -> mid-50s, needed MORE Framedelay frames, not fewer).
	See td-threaded-inference-optimization.md Round 2 for why and the numbers.

	gpu_mem_limit_bytes: optional cap on how far the CUDA EP's arena is allowed to grow.
	Left unset (ORT's own default) unless a caller needs to reserve VRAM headroom for TD's
	own rendering, which shares the same physical GPU and isn't otherwise coordinated with it.

	If a future caller ever batches a variable number of items into one session.run() call,
	pad to a fixed ceiling batch size first -- the CUDA EP caches cuDNN's convolution-
	algorithm selection per exact input shape, and a varying batch dimension re-pays a
	multi-second one-time search almost every call. See Round 5 for the full story.

	`cudnn_conv_algo_search: 'HEURISTIC'` avoids a different shape-cache stall (individual
	Conv nodes periodically taking ~200ms each even with a constant input shape, from the
	default 'EXHAUSTIVE' search's cache being evicted/re-triggered) -- see
	docs/learnings/mediapipe-landmarks.md. Applies globally, to every caller of this
	function, not just the script that first surfaced the symptom.
	"""
	cuda_options = {
		'device_id': 0,
		'cudnn_conv_algo_search': 'HEURISTIC',
	}
	if gpu_mem_limit_bytes is not None:
		cuda_options['gpu_mem_limit'] = gpu_mem_limit_bytes
	return [('CUDAExecutionProvider', cuda_options), 'CPUExecutionProvider'] # 'TensorrtExecutionProvider'

def log_model_details(session):
	printONNX('Session providers:', session.get_providers())
	printONNX('Inputs: -----------------')
	for i in session.get_inputs():
		printONNX('-', i.name, i.shape, i.type)
	printONNX("Outputs: ----------------")
	for o in session.get_outputs():
		printONNX('-', o.name, o.shape, o.type)
	printONNX("Input shape: ------------")
	input_shape = session.get_inputs()[0].shape
	has_dynamic_dims = any(isinstance(dim, str) for dim in input_shape)
	if has_dynamic_dims:
		# Use default size for MoveNet multipose (256x256)
		height, width = 256, 256
		printONNX(f"Model input shape is dynamic! Using default size: {height}x{width}")
	else:
		# Use the model's expected dimensions if they're specified
		batch_size, channels, height, width = input_shape
		printONNX(f"Model expects input shape: {input_shape}")

def check_providers(printfn, session):
	"""Log active execution providers and warn if running CPU-only (no CUDA EP) -- the
	standard tail every on_model_loaded() override across this project's ONNX scripts
	repeated verbatim (model-specific I/O-shape logging/sanity-checks stay in each
	script's own on_model_loaded(), only this generic tail is shared). `printfn` is
	normally the caller's own self.printONNX (keeps the '[ONNX]' log prefix consistent).
	Returns the active provider list in case a caller wants it."""
	active = session.get_providers()
	printfn(f"Active providers: {active}")
	if 'CUDAExecutionProvider' not in active:
		printfn("WARNING: Running on CPU only! CUDA provider not available.")
		printfn("  Install onnxruntime-gpu or check CUDA/cuDNN compatibility.")
	return active

# ========== Cyclic GC tax mitigation ==========
# Disabled process-wide (affects every script/extension in the TD session, not just ONNX)
# because Python's cyclic collector traversing this project's huge long-lived OP/Par object
# graph was causing ~2s freezes every 5-10s during real-time inference -- reference
# counting still frees everything except true cycles. See td-threaded-inference-
# optimization.md Round 11 for the full investigation and numbers, and Round 7/8 for the
# one place this project deliberately re-introduces a single manual gc.collect() anyway
# (a leaked worker-thread reference cycle, collected at a moment provably not mid-inference).
if gc.isenabled():
	gc.disable()
	printONNX('Disabled cyclic garbage collection to avoid periodic multi-second '
		'TD freezes during real-time inference (see onnx_inference_manager.py comment).')

# ========== Shared Performance Logging Functions ==========
# These can be used by both the ONNXInferenceManager class and standalone scripts (e.g. YuNet)

PERF_TABLE_HEADER = ['timestamp', 'frame', 'pre_ms', 'infer_ms', 'post_ms', 'total_ms', 'eff_fps', 'skipped']
PERF_TABLE_MAX_ROWS = 30  # Max data rows (excluding header)
PERF_LOG_INTERVAL = 1.0   # Seconds between log entries

def init_perf_table(tbl):
	"""Initialize a performance Table DAT with the standard header."""
	if tbl is None:
		return
	tbl.clear()
	tbl.appendRow(PERF_TABLE_HEADER)

def log_performance(tbl, last_perf_log_time, frame_count, pre_ms, infer_ms, post_ms, skipped):
	"""Write a performance row to a Table DAT. Returns updated last_perf_log_time.
	Call every frame — internally throttles to once per PERF_LOG_INTERVAL seconds."""
	if tbl is None:
		return last_perf_log_time
	
	now = time.perf_counter()
	if now - last_perf_log_time < PERF_LOG_INTERVAL:
		return last_perf_log_time
	
	total_ms = pre_ms + infer_ms + post_ms
	eff_fps = 1000.0 / total_ms if total_ms > 0 else 0
	
	tbl.appendRow([
		f"{time.time():.3f}",
		frame_count,
		f"{pre_ms:.2f}",
		f"{infer_ms:.2f}",
		f"{post_ms:.2f}",
		f"{total_ms:.2f}",
		f"{eff_fps:.1f}",
		skipped,
	])
	
	# Trim to max rows (header + data rows)
	while tbl.numRows > PERF_TABLE_MAX_ROWS + 1:
		tbl.deleteRow(1)  # Delete oldest data row (row 0 is header)

	return now


# ========== Shared Performance Tracking (in-memory, no DAT node needed) ==========
# In-memory rolling history plus self-installing read-only custom parameters on the parent
# COMP ("base comp") -- no per-network table_performance node required. The table-based
# functions above are unused by onCook but left in place; not removed.

PERF_HISTORY_LEN = 30    # number of recent (throttled) samples averaged for the readout
PERF_PAR_PAGE = 'Performance'
PERF_PAR_NAME = 'Effectivefps'
LATENCY_PAR_NAME = 'Pipelineframes'
AUTO_FRAMEDELAY_PAR_NAME = 'Autoframedelay'
PREPROCESS_MS_PAR_NAME = 'Preprocessms'
INFERENCE_MS_PAR_NAME = 'Inferencems'
POSTPROCESS_MS_PAR_NAME = 'Postprocessms'
SKIPPED_PCT_PAR_NAME = 'Frameskippedpct'

# How often the smoothed Pipelineframes/Framedelay estimate (and, sharing the same cadence,
# the per-stage timing/skip-rate metrics below) is recomputed and written -- a few times a
# second, not every frame (the raw per-frame number is noise, not signal; see
# _update_sync_estimate()/_update_perf_metrics()) and not just once a second either (fast
# enough to track a real change without a visible lag in the readout itself).
SYNC_UPDATE_INTERVAL = 0.2
# How far back the rolling window looks when computing the current estimate.
SYNC_WINDOW_SECONDS = 1.0


def _append_readonly_float(base_comp, name, label):
	"""Self-install a single read-only float custom par on PERF_PAR_PAGE if it doesn't
	already exist. Shared helper behind _ensure_perf_par()'s several near-identical pars."""
	if hasattr(base_comp.par, name):
		return
	page = next((pg for pg in base_comp.customPages if pg.name == PERF_PAR_PAGE), None)
	if page is None:
		page = base_comp.appendCustomPage(PERF_PAR_PAGE)
	p = page.appendFloat(name, label=label, size=1)
	p[0].default = 0.0
	p[0].readOnly = True  # scriptable, not UI-editable -- see Par.readOnly


def _ensure_perf_par(base_comp):
	"""Self-install this script's read-only performance/diagnostic custom parameters, plus
	an 'Auto Frame Delay' toggle, on the given COMP if they don't already exist. Shared
	across every ONNXInferenceManager subclass, so each script's containing COMP gets these
	automatically -- no manual per-network TD setup.

	Pipelineframes measures absTime.frame at capture time vs. at the moment that same
	frame's result is actually pushed to the output TOP -- the ONNX pipeline's OWN
	contribution to end-to-end latency (GPU readback delay + threaded inference
	handoff quantization + postprocess), in whole TD frames. This is deliberately NOT
	necessarily the same number as whatever a network's own cache/cacheselect Framedelay
	ends up needing empirically -- a gap between them would mean something else entirely
	(video source decode latency, TD's own render/present pipelining, etc.) is also
	contributing, not just this script. In practice (see _update_sync_estimate()) the two
	have been observed to track closely.

	The displayed Pipelineframes value is a rolling-MEDIAN estimate, not the raw per-frame
	reading -- see _update_sync_estimate() -- since the raw number is too noisy frame-to-
	frame to be a useful glanceable readout, and the median reports what's actually typical
	rather than a worst case.

	Preprocessms/Inferencems/Postprocessms are rolling AVERAGES (not max -- these are pure
	diagnostics, nothing downstream depends on them the way Framedelay depends on
	Pipelineframes, so a representative typical cost is more useful here than a worst-case
	spike) of last_preprocess_ms/last_inference_ms/last_postprocess_ms, see
	_update_perf_metrics(). Frameskippedpct is the rolling-average percentage of
	frames_skipped_final relative to each completed capture-to-publish cycle -- how much of
	this pipeline's own cadence is spent waiting on a still-busy worker thread, distinct
	from Effectivefps (which only reflects compute time, not skipped/wasted cook calls).

	Autoframedelay (default off) opts a comp into having Framedelay itself -- an existing,
	hand-authored custom par read by that network's own cache/cacheselect Framedelay
	expressions -- written automatically from this same smoothed estimate, instead of
	requiring manual tuning. Off by default so no existing comp's behavior changes unless
	explicitly enabled."""
	if base_comp is None:
		return
	_append_readonly_float(base_comp, PERF_PAR_NAME, 'Effective FPS (Inference)')
	_append_readonly_float(base_comp, LATENCY_PAR_NAME, 'Pipeline Latency (Frames)')
	_append_readonly_float(base_comp, PREPROCESS_MS_PAR_NAME, 'Preprocess (ms)')
	_append_readonly_float(base_comp, INFERENCE_MS_PAR_NAME, 'Inference (ms)')
	_append_readonly_float(base_comp, POSTPROCESS_MS_PAR_NAME, 'Postprocess (ms)')
	_append_readonly_float(base_comp, SKIPPED_PCT_PAR_NAME, 'Frames Skipped (%)')
	if not hasattr(base_comp.par, AUTO_FRAMEDELAY_PAR_NAME):
		page = next((pg for pg in base_comp.customPages if pg.name == PERF_PAR_PAGE), None)
		if page is None:
			page = base_comp.appendCustomPage(PERF_PAR_PAGE)
		p = page.appendToggle(AUTO_FRAMEDELAY_PAR_NAME, label='Auto Frame Delay')
		p[0].default = False


# ========== Previous-instance tracking for clean script-reload shutdown ==========
# Every onnx_*.py script's "Create global instance" section calls shutdown_and_register()
# to shutdown() its OWN previous manager instance before replacing it -- otherwise a script
# reload leaks a GPU-resident session forever (a leaked worker thread keeps the whole old
# instance reachable; see shutdown()'s docstring). A plain module-level global doesn't
# survive a Callbacks DAT text reassignment (fresh globals() each time); TD's own COMP-level
# store()/fetch() is NOT a substitute -- it's for project-persistent, picklable data, and a
# live manager instance is neither. See td-threaded-inference-optimization.md Round 7 for
# the full incident (a real TD crash from trying Storage instead) and Round 8 for why this
# registry is guarded against globals() (a /reload of this module reuses the same globals()
# dict rather than getting a fresh one, so a plain reassignment would wipe it).
if '_manager_registry' not in globals():
	_manager_registry = {}


def shutdown_and_register(comp_path, new_manager):
	"""Call from each onnx_*.py script's "Create global instance" section, AFTER
	constructing the new manager instance: shuts down whatever was previously
	registered for this exact comp_path (if anything), then registers the new one."""
	prev = _manager_registry.get(comp_path)
	if prev is not None:
		prev.shutdown()
	_manager_registry[comp_path] = new_manager


class ONNXInferenceManager:
	"""Base class for managing ONNX model loading and threaded inference in TouchDesigner."""
	
	def __init__(self):
		# TouchDesigner operator reference (set in onCook)
		self.scriptOp = None
		
		# Threaded model-loading state
		self.loading_thread = None
		self.is_loading = False
		self.load_error = None
		
		# Threaded inference state -- ONE persistent worker thread for the lifetime of
		# this manager instance (see _ensure_worker_started()/_worker_loop()), not a
		# fresh threading.Thread spawned every single frame. Removes OS thread-creation
		# overhead from the per-frame latency budget; a maxsize=1 queue enforces the
		# same "only one inference in flight at a time" invariant the old spawn-per-
		# frame code got for free, since onCook() only ever submits new work when
		# is_inferencing is False (i.e. the previous item has already been drained).
		self._worker_thread = None
		self._work_queue = queue.Queue(maxsize=1)
		self.is_inferencing = False
		self.inference_lock = threading.Lock()
		self.pending_result = None  # Results from background thread
		self.input_tensor_cache = None  # Pre-processed input for thread
		self.frames_skipped = 0  # Track how many frames we've skipped
		self.frames_skipped_final = 0  # Final count of skipped frames to report
		self._capture_abs_frame = None  # absTime.frame at the moment nA was captured
		self.last_pipeline_frames = 0  # measured capture->output latency, in TD frames
		self.numpy_array_delayed = True  # see onCook's capture branch -- live-toggleable

		# Auto Frame Delay -- see _update_sync_estimate(). Raw (timestamp, value) samples
		# of last_pipeline_frames, pruned to the last SYNC_WINDOW_SECONDS on each update.
		self._pipeline_frames_samples = []
		self._smoothed_pipeline_frames = 0.0
		self._last_sync_update_time = 0.0

		# Per-stage diagnostics -- see _update_perf_metrics(). Same rolling-window style as
		# above but plain rolling averages (no asymmetric decay -- pure diagnostics, nothing
		# downstream depends on these the way Framedelay depends on Pipelineframes).
		self._preprocess_ms_samples = []
		self._inference_ms_samples = []
		self._postprocess_ms_samples = []
		self._skipped_pct_samples = []
		self._last_perf_metrics_update_time = 0.0

		# Optional detector-submission throttle -- default 1 (every cook, no change for any
		# existing script). A subclass wanting this (see onnx_mediapipe_hands.py) sets
		# self.detector_interval directly (e.g. from a live custom par, read in the module-
		# level onCook wrapper before calling this class's onCook) rather than through a
		# constructor argument, so it stays a plain live-toggleable attribute like
		# numpy_array_delayed above. Skips capture/preprocess/worker-submission entirely on
		# throttled frames (the previous postprocessed output image just holds, same
		# principle as onnx_hsemotion.py's EMOTION_INTERVAL / onnx_mediapipe_hands.py's
		# LANDMARK_INTERVAL, generalized to the primary detector submission itself) --
		# fewer total GPU submissions per second, for pipelines heavy/contended enough that
		# updating every single frame isn't achievable or worth its cost.
		self.detector_interval = 1
		self._detector_frame_counter = 0

		# ONNX setup
		ort.preload_dlls(directory="")
		self.session = None  # ONNX session
		
		# Timing instrumentation
		self.last_preprocess_ms = 0
		self.last_inference_ms = 0
		self.last_postprocess_ms = 0
		self._frame_count = 0
		self._last_perf_log_time = 0.0
		self._perf_history = []  # recent effective-fps samples, see _record_perf_sample()

		# Output DAT references (resolved lazily in onCook)
		self._table_output = None  # table_output DAT for structured data
		self._table_performance = None  # table_performance DAT for timing logs
		self._dats_resolved = False
		
		# Utils
		self.npu = npu
	
	def printONNX(self, *args):
		"""Logging helper for ONNX operations."""
		print("[ONNX]", *args)

	def check_providers(self, session):
		"""Log active execution providers and warn if running CPU-only -- call this from
		on_model_loaded() as `self.check_providers(session)`. Thin wrapper around the
		module-level check_providers() that supplies self.printONNX automatically, so
		every subclass calls a real instance method instead of reaching through a
		self.onnx_util proxy attribute for a module that's since been folded into this
		one (see the "ONNX logging/provider helpers" section near the top of this file)."""
		return check_providers(self.printONNX, session)

	def _par_or_default(self, name, default):
		"""Read a live custom par by name if it exists on scriptOp, else fall back to the
		module-level constant default. Was previously copy-pasted verbatim into every
		ONNXInferenceManager subclass (identical body every time) -- centralized here
		since it has zero model-specific logic."""
		if self.scriptOp and hasattr(self.scriptOp.par, name):
			return getattr(self.scriptOp.par, name).eval()
		return default
	
	# ========== Output DAT Helpers ==========
	
	def _resolve_dats(self):
		"""Lazily resolve sibling DAT references from parent COMP."""
		if self._dats_resolved:
			return
		self._dats_resolved = True
		try:
			p = self.scriptOp.parent()
			self._table_output = p.op('table_output')
			self._table_performance = p.op('table_performance')
			if self._table_performance is not None:
				self._init_perf_table()
		except:
			pass
	
	@property
	def table_output(self):
		"""The table_output DAT for structured data output. None if it doesn't exist."""
		return self._table_output
	
	def _init_perf_table(self):
		"""Initialize performance table with header row."""
		init_perf_table(self._table_performance)
	
	def _log_performance(self):
		"""Write a performance row to table_performance (called at most once per second)."""
		self._last_perf_log_time = log_performance(
			self._table_performance,
			self._last_perf_log_time,
			self._frame_count,
			self.last_preprocess_ms,
			self.last_inference_ms,
			self.last_postprocess_ms,
			self.frames_skipped_final,
		)

	def _record_perf_sample(self):
		"""Throttled (once per PERF_LOG_INTERVAL) in-memory performance sample -- keeps
		the last PERF_HISTORY_LEN readings and pushes the rolling-average effective FPS
		to a read-only 'Effectivefps' custom par on the parent COMP ('base comp'). This
		is what onCook actually calls now; _log_performance()/the table_performance DAT
		above are left in place but unused (see module docstring)."""
		now = time.perf_counter()
		if now - self._last_perf_log_time < PERF_LOG_INTERVAL:
			return
		self._last_perf_log_time = now

		total_ms = self.last_preprocess_ms + self.last_inference_ms + self.last_postprocess_ms
		eff_fps = 1000.0 / total_ms if total_ms > 0 else 0.0
		self._perf_history.append(eff_fps)
		if len(self._perf_history) > PERF_HISTORY_LEN:
			self._perf_history.pop(0)

		avg_fps = sum(self._perf_history) / len(self._perf_history)
		try:
			base = self.scriptOp.parent()
			_ensure_perf_par(base)
			base.par.Effectivefps = round(avg_fps, 1)
		except:
			pass

	def _update_sync_estimate(self):
		"""Maintain a realistic (rolling-MEDIAN) estimate of pipeline latency, recomputed a
		few times a second (SYNC_UPDATE_INTERVAL) -- not every frame, which would just be
		noise, and not only once a second either, which would make the readout laggy to a
		real change.

		Call every frame (self.last_pipeline_frames is appended to the window each time);
		internally throttles the actual recompute+write.

		Uses the window's MEDIAN, not a rolling max. An earlier version tracked the max
		(with asymmetric decay: jump up immediately, ease down by 1/tick) specifically to
		drive Autoframedelay safely -- under-delaying there is a real correctness bug, the
		cache/cacheselect compensator would read a not-yet-ready or stale frame. But a
		direct sample of raw last_pipeline_frames (15 readings, 300ms apart) showed a
		mode/median of 3 with real frame-to-frame variance (2-4), not "typically 2 with
		rare spikes to 4-5" the way the max-based readout implied -- the max wasn't wrong,
		it was answering a different, deliberately worst-case question. The median reports
		what's ACTUALLY typical, and is naturally resistant to a rare outlier (a single
		contention-driven stall) without needing hand-tuned decay.

		Writes the estimate to Pipelineframes (replacing the raw single-frame number that
		used to go there -- too noisy frame-to-frame to be a useful glanceable readout, see
		_ensure_perf_par()'s docstring) and, only if Autoframedelay is on, to the network's
		own (pre-existing, hand-authored) Framedelay par. Autoframedelay is NOT recommended
		in practice for a cache/cacheselect Framedelay compensator regardless of which
		statistic drives it -- see Round 10 in td-threaded-inference-optimization.md: any
		change to Framedelay resizes/re-indexes the cache and is visibly glitchy on its own,
		independent of how accurate the value driving it is. Skipped entirely if the comp
		has no Framedelay par (no cache/cacheselect compensator set up) or Autoframedelay is
		off."""
		now = time.perf_counter()
		self._pipeline_frames_samples.append((now, self.last_pipeline_frames))

		if now - self._last_sync_update_time < SYNC_UPDATE_INTERVAL:
			return
		self._last_sync_update_time = now

		cutoff = now - SYNC_WINDOW_SECONDS
		self._pipeline_frames_samples = [(t, v) for t, v in self._pipeline_frames_samples if t >= cutoff]
		if not self._pipeline_frames_samples:
			return
		values = sorted(v for _, v in self._pipeline_frames_samples)
		mid = len(values) // 2
		self._smoothed_pipeline_frames = (
			values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2.0
		)

		try:
			base = self.scriptOp.parent()
			_ensure_perf_par(base)
			base.par.Pipelineframes = round(self._smoothed_pipeline_frames, 1)
			if (
				hasattr(base.par, 'Framedelay')
				and hasattr(base.par, AUTO_FRAMEDELAY_PAR_NAME)
				and getattr(base.par, AUTO_FRAMEDELAY_PAR_NAME).eval()
			):
				base.par.Framedelay = int(math.ceil(self._smoothed_pipeline_frames))
		except Exception:
			pass

	@staticmethod
	def _rolling_average(samples, new_value, now, window_seconds=SYNC_WINDOW_SECONDS):
		"""Append (now, new_value), prune anything older than window_seconds (samples are
		always appended in increasing time order, so the oldest entries are always at the
		front), and return the average of what remains. Shared by _update_perf_metrics()'s
		several near-identical rolling windows."""
		samples.append((now, new_value))
		cutoff = now - window_seconds
		while samples and samples[0][0] < cutoff:
			samples.pop(0)
		return sum(v for _, v in samples) / len(samples)

	def _update_perf_metrics(self):
		"""Maintain rolling-average per-stage timing (Preprocessms/Inferencems/
		Postprocessms) and frame-skip-rate (Frameskippedpct) diagnostics, recomputed at the
		same cadence as _update_sync_estimate() (SYNC_UPDATE_INTERVAL). Call once per
		completed capture-to-publish cycle, right alongside where last_preprocess_ms/
		last_inference_ms/last_postprocess_ms are all already finalized for this cycle.

		Unlike _update_sync_estimate()'s Pipelineframes, these are plain rolling averages,
		not a rolling max with asymmetric decay -- nothing downstream is driven by these
		values (see _ensure_perf_par()'s docstring), so a representative typical cost is
		more useful here than deliberately surfacing a worst-case spike.

		Frameskippedpct is frames_skipped_final (how many cook cycles were skipped, waiting
		on a still-busy worker thread, before THIS cycle's result became available) expressed
		as a percentage of the cycle's total length (skipped + 1, the +1 being this cycle's
		own successful cook) -- how much of this pipeline's own cadence is going to waiting,
		distinct from Effectivefps (which only reflects compute time, not idle/skipped cooks).
		"""
		now = time.perf_counter()
		if now - self._last_perf_metrics_update_time < SYNC_UPDATE_INTERVAL:
			return
		self._last_perf_metrics_update_time = now

		skipped_pct = 100.0 * self.frames_skipped_final / (self.frames_skipped_final + 1)
		avg_preprocess = self._rolling_average(self._preprocess_ms_samples, self.last_preprocess_ms, now)
		avg_inference = self._rolling_average(self._inference_ms_samples, self.last_inference_ms, now)
		avg_postprocess = self._rolling_average(self._postprocess_ms_samples, self.last_postprocess_ms, now)
		avg_skipped_pct = self._rolling_average(self._skipped_pct_samples, skipped_pct, now)

		try:
			base = self.scriptOp.parent()
			_ensure_perf_par(base)
			base.par.Preprocessms = round(avg_preprocess, 2)
			base.par.Inferencems = round(avg_inference, 2)
			base.par.Postprocessms = round(avg_postprocess, 2)
			base.par.Frameskippedpct = round(avg_skipped_pct, 1)
		except Exception:
			pass

	# ========== Methods to Override in Subclasses ==========
	
	def get_model_path(self):
		"""
		Return the full path to the ONNX model file.
		Must be implemented by subclass.
		"""
		raise NotImplementedError("Subclass must implement get_model_path()")
	
	def preprocess(self, nA):
		"""
		Preprocess input numpy array to model input tensor.
		Must be implemented by subclass.
		
		Args:
			nA: Raw numpy array from TouchDesigner texture
		
		Returns:
			Preprocessed input tensor ready for model inference
		"""
		raise NotImplementedError("Subclass must implement preprocess()")
	
	def postprocess(self, outputs):
		"""
		Postprocess model outputs to final numpy array for TouchDesigner.
		Must be implemented by subclass.
		
		Args:
			outputs: Raw outputs from model.run()
		
		Returns:
			Final numpy array (H, W, C) in float32 format for TouchDesigner
		"""
		raise NotImplementedError("Subclass must implement postprocess()")

	def run_inference(self, input_tensor):
		"""
		Actually invoke the session for one frame. Called from the persistent worker
		thread (see _worker_loop()) -- this is the ONLY thing that should run there;
		everything else (preprocess, postprocess) stays on the main thread.

		Default implementation covers every single-input model in this project:
		accepts either a plain array (wrapped as {first input name: array}) or a dict of
		{input name: array} for multi-input models, and calls the ordinary
		session.run(None, feed_dict).

		Override this for anything session.run() can't express directly -- e.g. a
		recurrent model needing IOBinding to keep per-frame state GPU-resident across
		calls (see onnx_rvm_seg.py), where the override manages its own persistent
		OrtValues/io_binding entirely and returns whatever plain data postprocess()
		expects (numpy arrays, not OrtValues -- do the device->host copy here, on the
		worker thread, not in postprocess).
		"""
		if isinstance(input_tensor, dict):
			return self.session.run(None, input_tensor)
		return self.session.run(None, {self.session.get_inputs()[0].name: input_tensor})

	def get_session_options(self):
		"""
		Override to customize ONNX session options.
		Returns sensible defaults with full graph optimization.
		"""
		opts = ort.SessionOptions()
		opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
		opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL  # Better for GPU-bound models
		return opts
	
	def on_model_loaded(self, session):
		"""
		Called after model loads successfully.
		Override to perform additional setup.
		"""
		pass

	def on_result_published(self):
		"""Called from onCook(), on the main thread, immediately after this frame's
		texture has been published via copyNumpyArray() -- and BEFORE the fall-through
		capture/dispatch of the NEXT frame (see onCook()'s "ORDERING NOTE" comment).

		Override to flush any side-channel outputs (Table DATs, CHOP channels, etc.)
		built from self.tracked_objects/whatever postprocess() just set, INSTEAD OF the
		older pending_table_update-flag-checked-by-the-wrapper-after-onCook-returns
		pattern most existing onnx_*.py scripts still use. Doing it here rather than
		after onCook() returns publishes those outputs one step earlier in the same
		cook -- before this frame's next capture is dispatched, not after -- which is
		both a cleaner mental model and closer to how tox/haxlib/ml/onnx/MovenetONNX.py's
		OutputSkeletonsToChop() ran (immediately after consuming a result, same call).
		Safe to do real TD operator access here: this only ever runs on the main thread,
		same as postprocess() itself, never the worker thread."""
		pass

	# ========== Model Loading ==========
	
	def loadONNX(self, scriptOp):
		"""Initiate threaded model loading."""
		if self.is_loading:
			self.printONNX("Model is already loading...")
			return
		
		# Reset session and start loading thread
		self.session = None
		scriptOp.par.Loadstatus = "loading"
		self.loading_thread = threading.Thread(target=self._load_model_thread)
		self.loading_thread.daemon = True
		self.loading_thread.start()
	
	def _load_model_thread(self):
		"""Background thread for loading ONNX model."""
		self.is_loading = True
		self.load_error = None
		
		try:
			self.printONNX('=============================================')
			self.printONNX("Starting ONNX model loading in background...")
			
			# Get model path from subclass
			model_path = self.get_model_path()
			self.printONNX("model:", model_path)
			
			# Get session options (if customized)
			sess_options = self.get_session_options()
			
			# Log ONNX environment
			log_onnx_options()
			providers_list = providers()

			# Load model
			if sess_options:
				temp_session = ort.InferenceSession(model_path, sess_options=sess_options, providers=providers_list)
			else:
				temp_session = ort.InferenceSession(model_path, providers=providers_list)

			self.printONNX('ONNX Device activated:', ort.get_device())
			self.printONNX('### session props -----------------------------------')

			log_model_details(temp_session)
			
			# Call subclass hook
			self.on_model_loaded(temp_session)
			
			# Only assign to global session when fully loaded
			self.session = temp_session
			self.printONNX("ONNX model loaded successfully!")
			self.printONNX('=============================================')
			
		except Exception as e:
			self.load_error = str(e)
			self.printONNX(f"Error loading ONNX model: {e}")
		finally:
			self.is_loading = False
	
	def get_loading_status(self):
		"""Returns status of model loading."""
		if self.session is not None:
			return "loaded"
		elif self.is_loading:
			return "loading"
		elif self.load_error:
			return f"error: {self.load_error}"
		else:
			return "not_loaded"

	def needs_prewarm(self):
		"""True while the model hasn't finished loading (or failed) and this scriptOp still
		needs to be force-cooked to make progress.

		Nothing wires most of these ONNX COMPs' outputs downstream by default, so TD's normal
		pull-based cooking never gives script1 a cook request on its own -- see
		schedule_prewarm_cook() for how this gets forced without a dedicated Execute DAT.
		Reads self.session/self.load_error directly (real per-session state, set fresh in
		__init__) rather than the persisted Loadstatus custom par, which can still show a
		stale 'loaded' string left over from the last time the project was saved.
		"""
		return self.session is None and self.load_error is None

	def schedule_prewarm_cook(self, scriptOp, callbacksDAT, delayFrames=1):
		"""Force scriptOp to cook on a future frame if the model still needs loading, entirely
		via Python -- no dedicated Execute DAT required.

		Safe to call from ANY context, including scriptOp's own Callbacks module at import
		time (module-level code that runs as part of scriptOp's own cook/compile): this method
		itself never calls .cook() directly, only td.run(), so it never reenters that compile.
		A direct, synchronous op('script1').cook(force=True) call from module-level code in
		scriptOp's own Callbacks DAT was tried and rejected by TD outright ("Unexpected error
		during compilation... check for cook loop", verified live) -- calling scriptOp.cook()
		is only safe once execution has actually moved to a later, unrelated frame, which is
		exactly what the deferred call below guarantees. See _prewarm_tick() for the half of
		this that actually cooks.

		Absolute op paths are baked into the deferred call (rather than using scriptOp/
		callbacksDAT/self directly) because td.run() strings execute later, outside of any
		Python closure -- there's nothing to close over by the time it actually runs.
		"""
		if not self.needs_prewarm():
			return
		# td.run(), not a bare run(): this module is imported via plain Python import (see the
		# module-level `import td`), so TD's DAT-script globals (run, op, ...) were never
		# injected into its own namespace the way they are in a directly-executed DAT script.
		td.run(
			f"op({callbacksDAT.path!r}).module.inference_manager._prewarm_tick("
			f"op({scriptOp.path!r}), op({callbacksDAT.path!r}))",
			delayFrames=delayFrames,
		)

	def _prewarm_tick(self, scriptOp, callbacksDAT):
		"""The actual force-cook, only ever invoked via schedule_prewarm_cook()'s deferred
		td.run() call -- never synchronously from scriptOp's own compile, so cooking it
		directly here is safe. Reschedules itself (through schedule_prewarm_cook, which
		re-checks needs_prewarm()) until the model resolves, then the chain stops on its own.
		"""
		if not self.needs_prewarm():
			return
		scriptOp.cook(force=True)
		self.schedule_prewarm_cook(scriptOp, callbacksDAT)

	# ========== Threaded Inference ==========

	def _ensure_worker_started(self):
		"""Lazily start the ONE persistent inference worker thread for this manager
		instance's lifetime (not in __init__, so a manager that never actually runs
		inference never pays for a thread at all). Also restarts the worker if the
		previous thread died/was shut down -- checking is_alive(), not just is None, so a
		manager instance that outlives its own worker thread can still resume inference.

		A worker thread left running past its manager's useful life is not a "minor leak":
		it keeps the whole manager instance (and its GPU-resident session) reachable and
		un-collectable, since the thread's own stack frame holds a live reference to self.
		See shutdown()/td-threaded-inference-optimization.md Round 7 for the real incident
		(GPU memory pegged at 96%/100% util after 20+ accumulated script reloads) and why
		every onnx_*.py script's "Create global instance" section calls shutdown() on the
		previous instance before constructing a new one."""
		if self._worker_thread is not None and self._worker_thread.is_alive():
			return
		self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
		self._worker_thread.start()

	def shutdown(self):
		"""Cleanly release this manager's GPU-resident ONNX Runtime session(s) and stop
		its background worker thread -- call this on the OLD manager instance right before
		a script reload replaces it with a new one, instead of leaking both. See
		_ensure_worker_started()'s docstring for the mechanism this prevents.

		Sends _worker_loop() its shutdown sentinel, then BLOCKS (joins with a timeout)
		until the thread actually exits -- without this join, the new model starts loading
		while the old one's CUDA arena is still being torn down, and both can briefly
		coexist on a GPU that's often already near its limit. See Round 8 for the
		save-triggered-reload incident this specifically fixes.

		Also clears any ort.InferenceSession-typed attribute via introspection (covers
		subclass-specific extra sessions, e.g. a landmark/emotion model, with no per-
		subclass override needed), then forces ONE manual gc.collect() -- safe here since
		this runs between models, not mid-inference, unlike the periodic collection this
		project disabled globally (see the module-level gc.disable() comment above)."""
		if self._worker_thread is not None and self._worker_thread.is_alive():
			try:
				self._work_queue.put_nowait(None)
			except queue.Full:
				pass  # a real inference is mid-flight; the thread exits on its NEXT get() instead
			self._worker_thread.join(timeout=5.0)
			if self._worker_thread.is_alive():
				self.printONNX('shutdown(): worker thread did not exit within 5s (stuck '
					'inference call?) -- proceeding anyway, but its session may not be freed')
		for name, val in list(vars(self).items()):
			if isinstance(val, ort.InferenceSession):
				setattr(self, name, None)
		gc.collect()

	def _worker_loop(self):
		"""Persistent background worker: blocks on the work queue between frames (near-
		zero cost while idle), runs ONLY session.run() (see run_inference()'s own
		docstring for why nothing else belongs here).

		Does NOT eliminate the dominant sources of input-to-output latency: TD's onCook
		only checks pending_result once per whole frame (a result landing mid-frame still
		waits for the next cook), and the CUDA EP shares the same physical GPU as TD's own
		rendering, uncoordinated with it.
		"""
		while True:
			input_tensor = self._work_queue.get()
			if input_tensor is None:  # shutdown sentinel -- sent by shutdown(), which then
				return               # joins this thread; see shutdown()'s docstring
			try:
				t0 = time.perf_counter()
				outputs = self.run_inference(input_tensor)
				self.last_inference_ms = (time.perf_counter() - t0) * 1000

				with self.inference_lock:
					self.pending_result = outputs

			except Exception as e:
				self.printONNX(f"Inference error: {e}")
				import traceback
				self.printONNX(traceback.format_exc())
			finally:
				self.is_inferencing = False
				self.frames_skipped_final = self.frames_skipped
	
	# ========== TouchDesigner Callbacks ==========
	
	def onSetupParameters(self, scriptOp):
		"""Setup custom parameters for the script operator."""
		page = scriptOp.appendCustomPage('Custom')
		# Add reload pulse
		page.appendPulse('Reloadonnx', label='Reload ONNX')
		# Add status info
		page.appendStr('Loadstatus', label='Load Status')
		scriptOp.par.Loadstatus = self.get_loading_status()
		return
	
	def onPulse(self, par):
		"""Handle custom pulse parameter triggers."""
		if par.name == 'Reloadonnx':
			self.session = None  # Reset the session
		return
	
	def onCook(self, scriptOp):
		"""
		Main inference loop called every frame by TouchDesigner.
		Handles model loading, result retrieval, and inference dispatching.
		
		Threading model (inspired by MoveNet pattern):
		- Preprocess runs on MAIN thread (fast TD buffer access, no copy needed)
		- Only session.run() runs on background thread (minimum thread time)
		- Postprocess runs on MAIN thread (safe TD operator access, no locks needed)
		"""
		# Update status parameter
		self.scriptOp = scriptOp
		status = self.get_loading_status()
		scriptOp.par.Loadstatus = status
		
		# Resolve sibling DATs on first cook
		if not self._dats_resolved:
			self._resolve_dats()
		
		# Make sure we've loaded the model
		if self.session is None:
			if not self.is_loading:
				self.loadONNX(scriptOp)
			# Return early if model isn't ready yet
			return
		
		# Check if we have a loading error
		if self.load_error:
			self.printONNX(f"Cannot process: {self.load_error}")
			return

		# Skip the actual per-frame work while TD is paused, rather than gating this via
		# CookLevel (AUTOMATIC vs ALWAYS). CookLevel is only reconsidered when TD decides
		# whether to attempt a cook at all -- once it settles on "not cooking" under
		# AUTOMATIC, nothing prompts it to re-check later, so resuming play doesn't nudge
		# it back (play/pause isn't a registered dependency of this op). Keeping
		# onGetCookLevel unconditionally ALWAYS means this op is always eligible to cook
		# every frame regardless of play state, and gating the real work here means the
		# very next actual cook after resuming naturally picks it back up -- no separate
		# re-triggering mechanism needed. Model loading above still proceeds while paused.
		if not scriptOp.time.play:
			return

		# Check if we have raw outputs from background thread
		with self.inference_lock:
			if self.pending_result is not None:
				raw_outputs = self.pending_result
				self.pending_result = None
				self.frames_skipped = 0
				
				# Postprocess on main thread (safe for TD operator access). THIS call is
				# where the frame's real payload is finalized: postprocess() sets
				# self.tracked_objects as a side effect, on top of returning output_img --
				# everything published below (this TOP's pixels, any Table DAT/CHOP output
				# a subclass flushes) comes from this exact same result, so they can never
				# disagree on WHICH detection cycle they represent.
				t0 = time.perf_counter()
				output_img = self.postprocess(raw_outputs)
				self.last_postprocess_ms = (time.perf_counter() - t0) * 1000

				# Ensure output is float32 for TouchDesigner
				if output_img.dtype != np.float32:
					output_img = output_img.astype(np.float32)

				scriptOp.copyNumpyArray(output_img)  # publish THIS frame's texture now

				# Give subclasses a chance to flush side-channel outputs (Table DATs,
				# etc.) built from the SAME postprocess() result, RIGHT NOW -- before the
				# next frame's capture/dispatch below, not after. See on_result_published()'s
				# own docstring for why this exists and the ordering it avoids.
				self.on_result_published()

				# See _ensure_perf_par()'s docstring -- this measures ONLY this script's
				# own capture->output latency, not whatever a network's cache/cacheselect
				# Framedelay ends up needing empirically.
				if self._capture_abs_frame is not None:
					try:
						self.last_pipeline_frames = td.absTime.frame - self._capture_abs_frame
					except Exception:
						pass
					self._update_sync_estimate()
					self._update_perf_metrics()

				# Record performance sample (once per second) -- see _record_perf_sample()
				self._frame_count += 1
				self._record_perf_sample()

				# Deliberately NOT returning here -- fall through to the capture/dispatch
				# code below so a fresh frame is captured and submitted in this SAME cook,
				# immediately after consuming this result, instead of injecting one extra
				# frame of latency waiting for a separate cook cycle (see
				# td-threaded-inference-optimization.md Round 9). is_inferencing is
				# reliably already False by the check just below: the worker thread sets
				# pending_result and then is_inferencing=False sequentially, with no
				# intervening I/O, before this lock is ever released.
				#
				# A subclass using the older pending_table_update-flag pattern (instead of
				# on_result_published() above) publishes its Table DAT one step later than
				# it needs to -- not a data bug, just avoidable CPU-time ordering. See
				# on_result_published()'s own docstring.

		# If inference is still running, skip this frame (natural frame skipping via threading)
		if self.is_inferencing:
			self.frames_skipped += 1
			return

		# Detector-submission throttle (see detector_interval's comment in __init__) --
		# skip capture/preprocess/submission entirely on throttled frames, holding
		# whatever output image is already there.
		if self.detector_interval > 1:
			self._detector_frame_counter += 1
			if self._detector_frame_counter % self.detector_interval != 0:
				return

		# Capture input and preprocess on main thread
		# Reading from TD's GPU staging buffer is fast on main thread (warm cache)
		# but very slow on bg thread (cache misses, mapped memory overhead).
		# Preprocess copies data into its own tensor buffer, so the bg thread
		# never touches the raw TD buffer.
		try:
			inputTex = scriptOp.inputs[0]
			# numpy_array_delayed is a live-toggleable instance attribute, not a constant,
			# so it can be flipped from an external /run probe without a code redeploy.
			# delayed=True (the default) avoids a CPU/GPU sync stall by accepting whatever
			# frame TD's own async GPU->CPU download queue happens to have ready -- that
			# queue's own depth is invisible to Pipelineframes, which only measures
			# latency from THIS call onward. See td-threaded-inference-optimization.md
			# Round 2 for the True vs False tradeoff (staleness vs stall duration).
			nA = inputTex.numpyArray(delayed=self.numpy_array_delayed)
			if nA is None:
				return
			# See the module-level `import td` comment for why this uses td.absTime
			# instead of the bare "pre-loaded global" convention. Kept in a try/except
			# anyway (belt-and-suspenders) since this is only the optional Pipelineframes
			# latency diagnostic -- its failure must never block the actual
			# capture/preprocess/inference path the way the bare-global version did.
			try:
				self._capture_abs_frame = td.absTime.frame
			except Exception:
				self._capture_abs_frame = None

			t0 = time.perf_counter()
			self.input_tensor_cache = self.preprocess(nA)
			self.last_preprocess_ms = (time.perf_counter() - t0) * 1000
			
		except Exception as e:
			self.printONNX(f"Error capturing input: {e}")
			return
		
		# Hand off to the persistent worker thread (runs ONLY session.run) -- see
		# _ensure_worker_started()/_worker_loop(). is_inferencing is set BEFORE the queue
		# put so onCook's "skip this frame" check above never races an empty queue against
		# a worker that hasn't picked the item up yet.
		self._ensure_worker_started()
		self.is_inferencing = True
		self._work_queue.put_nowait(self.input_tensor_cache)
