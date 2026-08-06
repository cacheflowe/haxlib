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
import threading
import queue
import gc
import numpy as np
import onnxruntime as ort
import math
# `td` is the one TD global this module imports explicitly (against the usual DAT-script
# convention of never importing it) -- absTime/op/parent/etc. are "pre-loaded globals" for
# a DAT's own directly-executed script code, but this is a plain imported module
# (python/util/), and that injection doesn't reliably reach here (confirmed live: worked
# during one dev session, then broke every ONNX script after a clean TD/machine restart).
# `import td` gives a real, stable module reference regardless of execution context.
import td

# Import util modules (will be available in TouchDesigner context)
import onnx_util  # Custom utilities for ONNX logging and details
import numpy_util as npu  # numpy utilities

# ========== Cyclic GC tax mitigation ==========
# Confirmed live (a /run-script diagnostic wrapping run_inference() and recording per-call
# timing over hundreds of samples): TD would periodically freeze for ~2 SECONDS every
# 5-10 seconds during real-time ONNX inference, fully recovering afterward -- looked at
# first like a GPU/CUDA stall, but disabling Python's cyclic garbage collector
# (gc.disable()) made the freezes disappear completely (0 outliers over 45s / ~700 calls,
# vs. 4 near-identical ~2075ms outliers in the previous 45s window with GC enabled). A live
# TD project has an enormous number of long-lived Python-wrapped OP/Par objects for the
# cyclic collector to traverse on every full (gen2) collection pass -- expensive purely
# from graph SIZE, not from actual garbage volume (gc.get_stats() showed only dozens of
# objects actually collected per gen2 pass). This is a known class of problem in real-time
# Python hosts generally (long-lived object graph + periodic stop-the-world tracing), not
# specific to this project's own code.
#
# Fully disabling gc is a PROCESS-WIDE change (affects every Python script/extension in
# this TD session, not just ONNX scripts), so it's placed here (once, at import time, for
# every consumer of this shared base class) rather than per-script. Reference-counting
# (Python's primary memory management, always active regardless of this setting) still
# immediately frees the overwhelming majority of objects -- this only stops CYCLE
# detection, so it's a real but usually small tradeoff: any code elsewhere in the project
# that creates true reference cycles (e.g. an extension holding a back-reference to its
# owner COMP) will leak that cycle's memory for the life of the process instead of having
# it swept up periodically. Judged acceptable here given the alternative is a
# multi-second UI freeze every few seconds during any real-time ONNX inference. If a slow
# memory growth is ever observed over very long (hours+) sessions, an explicit periodic
# `gc.collect()` scheduled at a deliberately-idle moment (not mid-inference) would be the
# next lever to reach for, rather than re-enabling automatic collection.
if gc.isenabled():
	gc.disable()
	onnx_util.printONNX('Disabled cyclic garbage collection to avoid periodic multi-second '
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
# Replaces the table_performance DAT approach above with an in-memory rolling history
# plus a self-installing read-only custom parameter on the parent COMP ("base comp").
# Every network stops needing its own table_performance node -- one less node whose
# existence/wiring has to be kept consistent per network, and the read-only par is a
# single glanceable number instead of a table to open. The table-based functions above
# are left as-is (unused by onCook now, but not removed) per instruction.

PERF_HISTORY_LEN = 30    # number of recent (throttled) samples averaged for the readout
PERF_PAR_PAGE = 'Performance'
PERF_PAR_NAME = 'Effectivefps'
LATENCY_PAR_NAME = 'Pipelineframes'


def _ensure_perf_par(base_comp):
	"""Self-install read-only 'Effective FPS' and 'Pipeline Latency (Frames)' custom
	parameters on the given COMP if they don't already exist. Shared across every
	ONNXInferenceManager subclass, so each script's containing COMP gets these
	automatically -- no manual per-network TD setup.

	Pipelineframes measures absTime.frame at capture time vs. at the moment that same
	frame's result is actually pushed to the output TOP -- the ONNX pipeline's OWN
	contribution to end-to-end latency (GPU readback delay + threaded inference
	handoff quantization + postprocess), in whole TD frames. This is deliberately NOT the
	same number as whatever a network's own cache/cacheselect Framedelay ends up needing
	empirically -- if Pipelineframes reads e.g. 2-3 but a real Framedelay of 6 is needed to
	visually resync, that gap is coming from somewhere else entirely (video source decode
	latency, TD's own render/present pipelining, etc.), not from this script."""
	if base_comp is None:
		return
	if not hasattr(base_comp.par, PERF_PAR_NAME):
		page = next((pg for pg in base_comp.customPages if pg.name == PERF_PAR_PAGE), None)
		if page is None:
			page = base_comp.appendCustomPage(PERF_PAR_PAGE)
		p = page.appendFloat(PERF_PAR_NAME, label='Effective FPS (Inference)', size=1)
		p[0].default = 0.0
		p[0].readOnly = True  # scriptable, not UI-editable -- see Par.readOnly
	if not hasattr(base_comp.par, LATENCY_PAR_NAME):
		page = next((pg for pg in base_comp.customPages if pg.name == PERF_PAR_PAGE), None)
		if page is None:
			page = base_comp.appendCustomPage(PERF_PAR_PAGE)
		p = page.appendFloat(LATENCY_PAR_NAME, label='Pipeline Latency (Frames)', size=1)
		p[0].default = 0.0
		p[0].readOnly = True


# ========== Previous-instance tracking for clean script-reload shutdown ==========
# Every onnx_*.py script's "Create global instance" section needs to find and
# shutdown() its OWN previous manager instance before replacing it (see
# ONNXInferenceManager.shutdown()'s docstring for why -- this is what stops a script
# reload from leaking a GPU-resident session forever). A plain module-level global
# doesn't survive a Callbacks DAT text reassignment (confirmed live: the re-executed
# module gets a genuinely fresh globals() namespace).
#
# Do NOT use TD's own COMP-level store()/fetch() for this, even though it's designed
# to survive exactly this kind of script recompilation -- it was tried first and
# caused a real, live-confirmed problem: TD's Storage mechanism is meant for data that
# gets serialized/persisted with the .toe project file, and a live manager instance
# holds fundamentally unpicklable resources (a threading.Thread, a threading.Lock, a
# GPU-resident ort.InferenceSession). Storing it live risked TD attempting to persist
# that object on save, which is the leading suspect behind an actual TD crash
# encountered while developing this fix, followed by a continuous model-reload loop
# after restart. This module-level dict is the safe replacement: it's a plain Python
# object living in a regular imported module (never serialized with the project,
# unlike a COMP's Storage), keyed by each script's own parent COMP path so multiple
# concurrent scripts don't collide.
#
# Guarded against globals() rather than a plain `_manager_registry = {}` so a /reload
# of THIS module (needed whenever this file itself changes) doesn't wipe it -- confirmed
# live this was a real gap, not just theoretical: /reload re-executes this module's
# top-level code against its EXISTING globals() (importlib.reload() mutates the same
# module object in place, it doesn't hand it a fresh namespace -- unlike a Callbacks
# DAT's text reassignment, which does), so a plain reassignment here discarded every
# already-registered instance while its worker thread and GPU session kept running
# undisturbed, just no longer tracked -- silently disabling this whole safety net for
# any of THOSE comps' next reload, for the rest of the TD session.
if '_manager_registry' not in globals():
	_manager_registry = {}


def shutdown_and_register(comp_path, new_manager):
	"""Call from each onnx_*.py script's "Create global instance" section, AFTER
	constructing the new manager instance: shuts down whatever was previously
	registered for this exact comp_path (if anything), then registers the new one.
	See the _manager_registry comment above for why this exists instead of a plain
	global or TD's own Storage."""
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
		self.onnx_util = onnx_util
		self.npu = npu
	
	def printONNX(self, *args):
		"""Logging helper for ONNX operations."""
		print("[ONNX]", *args)

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
			base.par.Pipelineframes = self.last_pipeline_frames
		except:
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
			if self.onnx_util:
				self.onnx_util.log_onnx_options()
				providers = self.onnx_util.providers()
			else:
				providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
			
			# Load model
			if sess_options:
				temp_session = ort.InferenceSession(model_path, sess_options=sess_options, providers=providers)
			else:
				temp_session = ort.InferenceSession(model_path, providers=providers)
			
			self.printONNX('ONNX Device activated:', ort.get_device())
			self.printONNX('### session props -----------------------------------')
			
			if self.onnx_util:
				self.onnx_util.log_model_details(temp_session)
			
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
	
	# ========== Threaded Inference ==========

	def _ensure_worker_started(self):
		"""Lazily start the ONE persistent inference worker thread for this manager
		instance's lifetime. Lazy (not started in __init__) so a manager that never
		actually runs inference (e.g. failed model load) never pays for a thread at all.

		Also restarts the worker if the previous thread died/was shut down (see
		shutdown()) -- checking is_alive(), not just is None, so a manager instance that
		outlives its own worker thread (e.g. after an explicit shutdown()) can still
		resume inference rather than silently never processing work again.

		CORRECTION to an earlier version of this comment, which called the tradeoff
		below "an accepted minor leak... not something that compounds during normal
		use" -- that was wrong, confirmed live: every script reload during active
		development (editing an onnx_*.py file and pushing it into a live Callbacks DAT)
		creates a NEW manager instance with its own new worker thread, and the OLD
		instance's worker thread has no shutdown hook tied to that reload -- it blocks
		forever on an empty queue.get(). A blocked-but-alive thread's own stack frame
		holds a live reference to `self` (the bound method it was started with), which
		keeps the ENTIRE old manager instance reachable and un-garbage-collectable --
		including its loaded ort.InferenceSession(s) and all the GPU/CUDA memory they
		hold. This is NOT near-zero cost: confirmed live with 20+ accumulated reloads
		across a single dev session, GPU memory usage climbed to 96% (15.7/16.4 GB) and
		utilization pegged at 100%, requiring a full TD restart. See shutdown() and every
		onnx_*.py script's "Create global instance" section, which now calls it on the
		previous instance before constructing a new one specifically to prevent this."""
		if self._worker_thread is not None and self._worker_thread.is_alive():
			return
		self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
		self._worker_thread.start()

	def shutdown(self):
		"""Cleanly release this manager's GPU-resident ONNX Runtime session(s) and stop
		its background worker thread -- call this on the OLD manager instance right
		before a script reload replaces it with a new one (see every onnx_*.py script's
		"Create global instance" section), instead of leaking both. See
		_ensure_worker_started()'s docstring for the full mechanism this prevents.

		Sends _worker_loop() its shutdown sentinel so the thread's `while True` loop
		actually returns instead of blocking forever, then BLOCKS (joins with a timeout)
		until it actually has -- confirmed live that without this join, the caller (the
		script's "Create global instance" section) immediately constructs and starts
		loading the NEW model while the OLD thread is still mid-exit, so both models'
		CUDA memory arenas briefly coexist. On a GPU already near its limit (this
		project's steady-state load across every ONNX_Playground comp routinely sits at
		80%+), that transient overlap during a save-triggered script reload (TD's file-
		sync noticing the backing .py changed and re-executing the module) is exactly
		what tips it into running out of memory, even though nothing is permanently
		leaked once the old thread finishes.

		Also proactively clears any ort.InferenceSession-typed attribute (self.session,
		plus any subclass-specific extra session like a landmark/emotion model) via
		introspection rather than requiring each subclass to override this, then forces
		ONE manual gc.collect() -- safe here specifically because this runs between
		models, not mid-inference, unlike the periodic collection this project disabled
		globally (see the module-level gc.disable() comment above) to avoid multi-second
		freezes. A worker thread that held the last reference to a bound method of self
		creates a genuine reference cycle (self -> _worker_thread -> _target -> self);
		CPython's own threading module clears _target once the thread function returns,
		which normally breaks that cycle via plain refcounting alone -- but any OTHER
		cycle this class (or a subclass) doesn't yet know about would otherwise sit
		uncollected for the life of the process with cyclic GC off."""
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
		"""Persistent background worker -- replaces the old pattern of spawning a brand
		new OS thread every single frame. Blocks on the work queue between frames (near-
		zero cost while idle) and starts session.run() the instant work is queued, saving
		the thread-creation/startup overhead a fresh threading.Thread paid every frame.

		This tightens scheduling slightly but does NOT eliminate the dominant sources of
		input-to-output latency: TD's onCook only checks pending_result once per whole
		frame (so a result that lands mid-frame still waits for the next cook to be
		picked up), and the CUDA EP shares the same physical GPU as TD's own rendering,
		which isn't otherwise coordinated with inference's own GPU submissions.
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
				
				# Update performance metrics if available
				try:
					self.opPerformance.par.const0value = self.frames_skipped_final
					if self.frames_skipped_final > 0:  # Prevent div by zero
						self.opPerformance.par.const1value = math.floor(60 / self.frames_skipped_final)
				except:
					pass  # Performance constants not available
				
				# Postprocess on main thread (safe for TD operator access)
				t0 = time.perf_counter()
				output_img = self.postprocess(raw_outputs)
				self.last_postprocess_ms = (time.perf_counter() - t0) * 1000

				# Ensure output is float32 for TouchDesigner
				if output_img.dtype != np.float32:
					output_img = output_img.astype(np.float32)

				scriptOp.copyNumpyArray(output_img)

				# See _ensure_perf_par()'s docstring -- this measures ONLY this script's
				# own capture->output latency, not whatever a network's cache/cacheselect
				# Framedelay ends up needing empirically.
				if self._capture_abs_frame is not None:
					try:
						self.last_pipeline_frames = td.absTime.frame - self._capture_abs_frame
					except Exception:
						pass

				# Record performance sample (once per second) -- see _record_perf_sample()
				self._frame_count += 1
				self._record_perf_sample()
				
				return  # Early return after outputting result
		
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
			# numpy_array_delayed is a live-toggleable instance attribute (not a constant)
			# specifically so it can be flipped from an external /run probe without a code
			# redeploy -- see the class docstring's latency-diagnostic note. delayed=True
			# (the default) avoids a CPU/GPU sync stall by accepting whatever frame TD's
			# own async GPU->CPU download queue happens to have ready; that queue's own
			# depth is invisible to Pipelineframes (which only measures latency AFTER this
			# call returns), so it's the prime remaining suspect when Pipelineframes reads
			# much lower than an empirically-needed Framedelay.
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
