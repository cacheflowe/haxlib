import onnxruntime as ort


def printONNX(*args):
	print("[ONNX]", *args)

def log_onnx_options():
	printONNX('version', ort.__version__)
	# print('Available providers:')
	# for provider in ort.get_available_providers():
	# 	print('-', provider)

def providers(gpu_mem_limit_bytes=None):
	"""CUDA (falling back to CPU) execution provider list, with explicit CUDA EP options.

	NOTE: this previously also set arena_extend_strategy='kSameAsRequested' on the theory
	that a fixed per-frame input shape wouldn't need ORT's default doubling-growth
	arena. Measured live against rf-detr-seg-nano.onnx, that setting was a real
	regression (effective fps dropped from 80s to mid-50s, and the project's
	frame-delay compensator needed MORE frames, not fewer) -- 'kSameAsRequested' controls
	how the arena EXTENDS when it needs more memory than it currently has cached, and if
	the model's actual internal allocation pattern isn't byte-identical every call, it
	forces the arena to re-extend (a real, synchronizing cudaMalloc) far more often than
	the default 'kNextPowerOfTwo', which rounds generously so it rarely needs to re-extend
	at all. Reverted -- don't re-add without measuring the isolated effect first.

	gpu_mem_limit_bytes: optional cap on how far the CUDA EP's arena is allowed to grow.
	Left unset (ORT's own default, effectively unlimited) unless a caller has a specific
	reason to reserve VRAM headroom -- e.g. for TD's own rendering pipeline, which shares
	the same physical GPU as inference and isn't otherwise coordinated with it.

	If a future caller ever batches a variable number of items into one session.run()
	call (e.g. per-detection secondary classification across N tracked instances), be
	aware the CUDA EP caches cuDNN's convolution-algorithm selection PER EXACT INPUT
	SHAPE -- confirmed live (onnx_hsemotion.py) that a varying batch dimension means
	almost every call hits a brand-new shape and re-pays a multi-second one-time search,
	turning a batching "optimization" into a severe regression. Pad to a fixed ceiling
	batch size instead of using the real (varying) count -- see
	.ai/skills/td-threaded-inference-optimization.md's "Round 5" for the full story and
	timing numbers.

	`cudnn_conv_algo_search: 'HEURISTIC'` -- confirmed live via onnxruntime's own
	`enable_profiling` trace (see docs/learnings/mediapipe-landmarks.md) that even with a
	genuinely CONSTANT input shape every call, individual depthwise Conv nodes
	periodically took ~200ms EACH (vs. microseconds normally) -- ~9 of them summing to a
	~2-SECOND total stall that froze the whole TD app, recurring every 15-90+ seconds with
	no obvious trigger. This is the default 'EXHAUSTIVE' algorithm search's cache being
	evicted/re-triggered periodically, not a one-time per-shape cost -- plausibly from
	cache pressure when multiple sessions/models (e.g. a detector + a separate landmark
	model, as in every onnx_mediapipe_*.py script) share the same process-wide cuDNN
	algorithm cache. 'HEURISTIC' picks a fast, good-enough algorithm via cuDNN's built-in
	heuristics instead of an actual timed benchmark-and-cache search, eliminating this
	class of stall entirely -- there is no longer a cache to evict, so there's nothing to
	periodically re-pay. Confirmed via the same profiling trace: no individual Conv node
	exceeded a few ms after this was set. Applies globally (every caller of this shared
	providers() function), not just the script that first surfaced the symptom.
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
	# printONNX('- Model description:', session.get_modelmeta().description)
	# printONNX('- Model version:', session.get_modelmeta().version)
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
