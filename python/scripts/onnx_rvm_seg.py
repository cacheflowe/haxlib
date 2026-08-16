import os
import numpy as np
import onnxruntime as ort

# custom util imports
import numpy as npu
import onnx_inference_manager

# Import the base inference manager
ONNXInferenceManager = onnx_inference_manager.ONNXInferenceManager

# ==================== CONFIGURATION ====================
# Robust Video Matting (RVM, https://github.com/PeterL1n/RobustVideoMatting), ONNX export
# per their own onnx branch inference guide. Architecturally NOTHING like the other seg
# scripts in this project (onnx_yolo26_seg.py, onnx_rfdetr_seg.py) -- there are no boxes,
# no classes, no per-instance identity, and therefore no ByteTracker at all. RVM is a
# single dense foreground/alpha matte for the WHOLE frame, produced by a RECURRENT network
# that carries 4 hidden-state tensors forward from frame to frame for temporal
# consistency (this is what makes RVM's matte stable/non-flickery on video compared to a
# frame-independent segmenter) -- the recurrent state is the one genuinely new piece of
# machinery this script adds to the shared ONNXInferenceManager base class.
MODEL_FILENAME = 'rvm_mobilenetv3_fp32.onnx'

# Model I/O (per session.get_inputs()/get_outputs()):
#   inputs:  src [B,3,H,W] float32, r1i/r2i/r3i/r4i [B,C,H,W] float32 (C=16/20/40/64,
#            only visible via r1o..r4o's output shapes -- dynamic dims mean ORT itself
#            doesn't expose these numbers up front), downsample_ratio [1] float32
#   outputs: fgr [B,3,H,W], pha [B,1,H,W], r1o/r2o/r3o/r4o (next frame's r1i..r4i)
# Every tensor in this export is float32 (the "fp32" in the filename) -- unlike RVM's
# upstream inference guide's fp16 example, no dtype casting is needed anywhere here.
# Initial recurrent state is a zero tensor of shape [1,1,1,1] per frame 0 -- the model
# broadcasts this internally to whatever the real per-stage feature-map shape turns out
# to be; every frame after that just feeds back whatever r1o..r4o actually were, whatever
# shape that happens to be. This script never needs to know those shapes itself.
RECURRENT_INPUT_NAMES = ['r1i', 'r2i', 'r3i', 'r4i']
RECURRENT_OUTPUT_NAMES = ['r1o', 'r2o', 'r3o', 'r4o']

# RVM's own speed/quality knob: internally downsamples `src` by this fraction before its
# (relatively heavy) encoder/decoder, then upsamples back to native resolution via a
# lightweight guided filter that references the full-res frame for sharp edges. This is a
# DIFFERENT lever from this network's own Inputwidth par (which controls the TD-side
# working resolution fed into `src` at all) -- Inputwidth picks how big a frame RVM sees,
# Downsampleratio picks how much of THAT frame its expensive encoder actually processes.
# 0.25 is RVM's own commonly recommended default for HD-ish source video.
DOWNSAMPLE_RATIO = 0.25

# Which combination of RVM's outputs to visualize. 'rgba': fgr (color-decontaminated
# foreground, edges cleaned of background bleed) as RGB + pha as alpha -- a ready-to-
# composite cutout, and the pairing RVM was actually trained to produce jointly. 'alpha':
# pha alone, replicated across RGB (matching this project's other seg scripts' "soft
# matte" convention) with alpha=1 -- useful when compositing against the ORIGINAL source
# video's own color instead of RVM's color-corrected fgr.
OUTPUT_MODE = 'rgba'

# Multiply RGB by alpha before output (RGBA Cutout mode only). RVM's raw fgr is straight
# (unpremultiplied) color; TD's own compositing (Over TOP, Composite TOP, etc.) generally
# expects premultiplied alpha, and feeding it straight color produces a visible edge
# mismatch. On by default so the output composites correctly with standard TD nodes with
# no extra step required.
PREMULTIPLY_ALPHA = True


class RVMMattingInference(ONNXInferenceManager):
	"""RVM video matting via IOBinding with GPU-resident recurrent state.

	Per RVM's own inference guide, the naive `session.run()` loop round-trips the 4
	recurrent tensors through CPU on every single frame for no reason -- they're pure
	intermediate state, never touched by anything outside this loop. `run_inference()`
	below overrides the base class's default session.run() call entirely with an
	`io_binding` that keeps `r1i..r4i` as CUDA-resident `OrtValue`s across calls, rebound
	directly from the previous call's `r1o..r4o` output OrtValues (zero-copy) -- only
	`src` (a genuinely new frame every time) and `downsample_ratio` (small, and can change
	live if the user tweaks the par) cross the CPU<->GPU boundary each frame; `fgr`/`pha`
	are copied back to CPU since postprocess() needs real numpy arrays for TD.

	This match state is pure sequential instance state (self._rec), safe without a lock:
	run_inference() only ever executes on the persistent worker thread, and the base
	class's is_inferencing/queue gating guarantees at most one call in flight at a time --
	preprocess()/postprocess() (main thread) never touch it.
	"""

	def __init__(self):
		super().__init__()
		# numpy_array_delayed=False regressed inference time here even though it helped
		# onnx_rfdetr_seg.py -- see Round 2 in td-threaded-inference-optimization.md. Left
		# at the base class default (True); don't flip without re-measuring cleanly.
		self.opOutputTableDAT = parent().op('table_output')
		# CUDA-resident recurrent state -- (re)initialized in on_model_loaded() and by the
		# Resetstate pulse. None until a session exists (OrtValue needs a CUDA context).
		self._rec = None
		self._io_binding = None
		self._reset_state_requested = False
		self._input_tensor_buf = None
		self._input_buf_shape = None
		self._output_buf = None
		self._output_buf_shape = None
		# Plain float, set by preprocess() (main thread) each frame, read by
		# run_inference() (worker thread) -- see preprocess()'s comment for why this
		# can't just be a live TD par read inside run_inference() itself.
		self._current_downsample_ratio = np.array([DOWNSAMPLE_RATIO], dtype=np.float32)
		self._current_output_mode = OUTPUT_MODE
		self._last_error = None  # last run_inference exception text, for diagnostics

	def onSetupParameters(self, scriptOp):
		"""Add RVM-specific parameters alongside base class params."""
		super().onSetupParameters(scriptOp)
		page = scriptOp.appendCustomPage('RVM')
		p = page.appendFloat('Downsampleratio', label='Downsample Ratio', size=1)
		p[0].default = DOWNSAMPLE_RATIO
		p[0].min = 0.05
		p[0].max = 1.0
		p[0].clampMin = True
		p[0].clampMax = True
		p[0].help = ("RVM's own internal speed/quality knob -- downsamples the frame by this "
			"fraction before its encoder/decoder, then upsamples back to full resolution via a "
			"lightweight guided filter. Lower = faster but softer/less fine detail (hair, "
			"fingers); higher = sharper but slower. NOT the same as this network's Inputwidth par "
			"-- Inputwidth picks how big a frame RVM sees at all, this picks how much of that "
			"frame its expensive encoder actually processes.")
		scriptOp.par.Downsampleratio = DOWNSAMPLE_RATIO
		p = page.appendMenu('Outputmode', label='Output Mode')
		p[0].menuNames = ['rgba', 'alpha']
		p[0].menuLabels = ['RGBA Cutout (fgr+pha)', 'Alpha Only']
		p[0].default = OUTPUT_MODE
		p[0].help = ("RGBA Cutout: RVM's color-decontaminated foreground (edges cleaned of "
			"background bleed) as RGB, with alpha as pha -- a ready-to-composite cutout. Alpha "
			"Only: pha alone as a white-on-black matte (RGB=alpha, A=1) -- use this to composite "
			"against the ORIGINAL source video's own color instead of RVM's recolored fgr.")
		scriptOp.par.Outputmode = OUTPUT_MODE
		p = page.appendToggle('Premultiplyalpha', label='Premultiply RGB by Alpha')
		p[0].default = PREMULTIPLY_ALPHA
		p[0].help = ("Multiplies RGB by alpha before output (RGBA Cutout mode only -- Alpha Only "
			"is unaffected, RGB already equals alpha there). RVM's raw fgr is straight/unpremultiplied "
			"color, and can still carry a little background color bleed at soft edges that its own "
			"decontamination doesn't fully clean up. TD's own compositing (Over TOP, Composite TOP, "
			"etc.) generally expects premultiplied alpha -- feeding it straight color causes exactly "
			"the edge mismatch a downstream Math TOP set to 'Pre-Multiply RGB by Alpha' fixes after "
			"the fact; this does the same multiply once here instead. Turn off only if you need "
			"straight color for further grading/color-keying before compositing (premultiplied color "
			"gets very dark at low alpha and distorts those operations).")
		scriptOp.par.Premultiplyalpha = PREMULTIPLY_ALPHA
		page.appendPulse('Resetstate', label='Reset Recurrent State')
		scriptOp.par.Resetstate.help = ("Zeroes RVM's 4 recurrent hidden-state tensors. RVM "
			"assumes temporal continuity between consecutive frames -- after a hard cut or a "
			"video loop restart, the carried-over state describes a scene that's no longer "
			"there, which can ghost/smear into the next real frames until it naturally decays. "
			"Pulse this right after a cut/loop point to avoid that.")

	def onPulse(self, par):
		super().onPulse(par)
		if par.name == 'Resetstate':
			self._reset_state_requested = True

	def get_model_path(self):
		"""Return path to the RVM matting model."""
		model_dir = os.path.join(project.folder, 'data', 'ml', 'rvm')
		return os.path.join(model_dir, MODEL_FILENAME)

	def on_model_loaded(self, session):
		"""Log model I/O and set up the persistent IOBinding + zeroed recurrent state --
		both live for the lifetime of this session (rebuilt only on model reload or an
		explicit Resetstate pulse), matching RVM's own inference guide's IOBinding
		example."""
		outputs = session.get_outputs()
		self.printONNX(f"RVM model outputs ({len(outputs)}):")
		for o in outputs:
			self.printONNX(f"  name='{o.name}' shape={o.shape} type={o.type}")
		inputs = session.get_inputs()
		for inp in inputs:
			self.printONNX(f"  input name='{inp.name}' shape={inp.shape} type={inp.type}")
		self.check_providers(session)

		# The base class calls on_model_loaded(session) BEFORE assigning self.session, so
		# self.session is still None here -- set it early since _recreate_io_binding() needs
		# self.session (it's also called later from run_inference(), which has no `session`
		# param). See Round 4 in td-threaded-inference-optimization.md.
		self.session = session
		self._recreate_io_binding()

	def _recreate_io_binding(self):
		"""(Re)build the IOBinding's output bindings AND reset recurrent state together.

		A recurrent-state reset alone isn't enough to recover from a large resolution
		change -- the output bindings themselves (bound once at load, no explicit shape)
		get stuck erroring every frame after that. Recreating the io_binding is cheap and
		there's no reliable way to tell a small aspect change from a large resolution
		change apart, so always do both together. See Round 4 in
		td-threaded-inference-optimization.md."""
		self._io_binding = self.session.io_binding()
		for name in ['fgr', 'pha'] + RECURRENT_OUTPUT_NAMES:
			self._io_binding.bind_output(name, 'cuda')
		self._reset_recurrent_state()

	def _reset_recurrent_state(self):
		"""Zero-value [1,1,1,1] CUDA OrtValues -- RVM's documented initial recurrent
		state; the model broadcasts these internally to each stage's real feature-map
		shape on the first real frame."""
		self._rec = [
			ort.OrtValue.ortvalue_from_numpy(np.zeros([1, 1, 1, 1], dtype=np.float32), 'cuda')
			for _ in RECURRENT_INPUT_NAMES
		]

	def preprocess(self, nA):
		"""Preprocess the source frame for RVM. Assumes TD has already resized input to
		this network's working resolution upstream (fit_square_sm, aspect-preserving --
		see the network's Inputwidth par and constant2's aspect expression; UNLIKE the
		other seg scripts here, RVM is fully convolutional and doesn't need a SQUARE
		input, only a sane fixed working size for consistent performance). No ImageNet
		normalization -- RVM's own spec wants plain 0-1 RGB, which is exactly what TD's
		numpyArray() already delivers."""
		self.original_h, self.original_w = nA.shape[:2]
		num_channels = nA.shape[2] if len(nA.shape) == 3 else 1

		needed = (1, 3, self.original_h, self.original_w)
		if self._input_buf_shape != needed:
			# A resolution change means the recurrent state's per-stage spatial shapes no
			# longer match what this resolution's feature maps need, which crashes on the
			# next inference (see Round 4 in td-threaded-inference-optimization.md). This
			# network's source is a switch1 cycling between clips of different aspect
			# ratios, so a live source switch hits this path routinely -- request a reset
			# unconditionally on any shape change (including the harmless first-frame case)
			# rather than relying solely on the manual Resetstate pulse.
			if self._input_buf_shape is not None:
				self._reset_state_requested = True
			self._input_tensor_buf = np.empty(needed, dtype=np.float32)
			self._input_buf_shape = needed

		if num_channels >= 3:
			flipped = nA[::-1, :, :3]  # flip V + drop alpha (view, no alloc)
		else:
			img = self.npu.flip_v(nA)
			flipped = self.npu.grayscale_to_rgb(img)

		self._input_tensor_buf[0, 0] = flipped[:, :, 0]
		self._input_tensor_buf[0, 1] = flipped[:, :, 1]
		self._input_tensor_buf[0, 2] = flipped[:, :, 2]

		# Read the Downsampleratio par HERE, on the main thread -- NOT inside
		# run_inference(), which runs on the persistent worker thread. Reading a TD par
		# from a background thread crashes TD (see Round 3 in
		# td-threaded-inference-optimization.md) -- stash the plain float value now so
		# run_inference() only ever touches an ordinary Python attribute, never
		# self.scriptOp, from the worker thread.
		self._current_downsample_ratio = np.array(
			[self._par_or_default('Downsampleratio', DOWNSAMPLE_RATIO)], dtype=np.float32
		)
		# Same reasoning, same thread rule -- read Outputmode here so run_inference() can
		# skip copying fgr back to CPU entirely when Alpha Only mode doesn't need it
		# (fgr is 3 channels vs pha's 1 -- a real, avoidable chunk of GPU->CPU bandwidth
		# every single frame it isn't actually used).
		self._current_output_mode = self._par_or_default('Outputmode', OUTPUT_MODE)

		return self._input_tensor_buf

	def run_inference(self, input_tensor):
		"""Override the base class's plain session.run() -- see class docstring. Runs on
		the persistent worker thread -- must NEVER touch self.scriptOp/TD pars directly
		(see preprocess()'s comment on _current_downsample_ratio for why). Rebinds
		`src`/`downsample_ratio` fresh from CPU each call, rebinds `r1i..r4i` from the
		PREVIOUS call's output OrtValues (GPU-resident, zero-copy), runs, then copies only
		`fgr`/`pha` back to CPU (postprocess needs real numpy arrays) while the new
		r1o..r4o OrtValues become next call's recurrent input state directly."""
		if self._reset_state_requested:
			self._recreate_io_binding()
			self._reset_state_requested = False

		downsample_ratio = self._current_downsample_ratio

		def bind_and_run():
			# Reads self._io_binding fresh each call (not a closed-over local) so a
			# mid-retry _recreate_io_binding() swap is actually picked up on the retry.
			io = self._io_binding
			io.bind_cpu_input('src', input_tensor)
			for name, rec_value in zip(RECURRENT_INPUT_NAMES, self._rec):
				io.bind_ortvalue_input(name, rec_value)
			io.bind_cpu_input('downsample_ratio', downsample_ratio)
			self.session.run_with_iobinding(io)
			return io.get_outputs()

		try:
			fgr_ov, pha_ov, *self._rec = bind_and_run()
		except RuntimeError as e:
			# Recurrent state (and, for a large enough resolution change, the io_binding's
			# own output bindings) carry shape assumptions tied to whatever
			# resolution/downsample_ratio produced them, and can mismatch even between
			# consecutive frames at an unchanged resolution -- see Round 4 in
			# td-threaded-inference-optimization.md. Self-heal by recreating the io_binding
			# and resetting to the broadcastable zero state, then retrying once, rather than
			# leaving the pipeline wedged in a repeating error loop -- a dropped frame of
			# temporal consistency is a much smaller cost than a stuck, erroring script.
			self._last_error = str(e)  # plain attribute, safe to inspect cross-thread
			self.printONNX(f"Inference shape mismatch, recreating io_binding and retrying: {e}")
			self._recreate_io_binding()
			fgr_ov, pha_ov, *self._rec = bind_and_run()

		# Alpha Only mode never looks at fgr (see postprocess()) -- skip its GPU->CPU copy
		# entirely rather than throwing away 3 channels of transferred data every frame.
		fgr_np = None if self._current_output_mode == 'alpha' else fgr_ov.numpy()
		return (fgr_np, pha_ov.numpy())

	def postprocess(self, outputs):
		"""Combine RVM's fgr/pha into a single RGBA (or alpha-only) image for TD. fgr is
		None in Alpha Only mode (see run_inference() -- its GPU->CPU copy is skipped
		entirely there since this method never reads it in that mode)."""
		fgr, pha = outputs  # each (1, C, H, W), CHW, 0-1 float32, native model orientation
		h, w = pha.shape[2], pha.shape[3]

		needed_shape = (h, w, 4)
		if self._output_buf is None or self._output_buf_shape != needed_shape:
			self._output_buf = np.empty(needed_shape, dtype=np.float32)
			self._output_buf_shape = needed_shape

		# Deliberately reuse self._current_output_mode (the value run_inference() already
		# used to decide whether to copy fgr back at all) rather than re-reading the
		# Outputmode par fresh here -- if the user flips the par between preprocess()
		# capturing that decision and postprocess() rendering this same frame's result,
		# a fresh read here could disagree with whether fgr is actually None, crashing on
		# fgr[0,0]. Reusing the same captured value keeps the two guaranteed consistent.
		output_mode = self._current_output_mode
		alpha = pha[0, 0]
		if output_mode == 'alpha':
			self._output_buf[:, :, 0] = alpha
			self._output_buf[:, :, 1] = alpha
			self._output_buf[:, :, 2] = alpha
			self._output_buf[:, :, 3] = 1.0
		else:
			premultiply = self._par_or_default('Premultiplyalpha', PREMULTIPLY_ALPHA)
			mult = alpha if premultiply else 1.0
			self._output_buf[:, :, 0] = fgr[0, 0] * mult
			self._output_buf[:, :, 1] = fgr[0, 1] * mult
			self._output_buf[:, :, 2] = fgr[0, 2] * mult
			self._output_buf[:, :, 3] = alpha

		# Flip Y-axis for TouchDesigner (model uses top-down, TD uses bottom-up) --
		# same convention as every other script in this project.
		return self.npu.flip_v(self._output_buf)


# Create global instance -- shut down any PREVIOUS instance first (releases its
# GPU-resident ONNX Runtime session(s) and stops its worker thread) so a script
# reload during active development doesn't leak both -- see
# onnx_inference_manager.shutdown_and_register()'s docstring for the full
# mechanism this avoids (and why it's NOT TD's own store()/fetch(), which risked
# a real crash trying to persist a live, unpicklable manager instance).
inference_manager = RVMMattingInference()
onnx_inference_manager.shutdown_and_register(parent().path, inference_manager)

# TouchDesigner callback wrappers that delegate to the manager
def onSetupParameters(scriptOp):
	return inference_manager.onSetupParameters(scriptOp)


def onPulse(par):
	return inference_manager.onPulse(par)


def onCook(scriptOp):
	inference_manager.onCook(scriptOp)


def onGetCookLevel(scriptOp: scriptCHOP) -> CookLevel:
	"""See onnx_yolo26_seg.py's identical method for why this is unconditionally ALWAYS
	rather than AUTOMATIC."""
	return CookLevel.ALWAYS
