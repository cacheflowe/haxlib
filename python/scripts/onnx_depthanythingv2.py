import os
import numpy as np

# custom util imports
import numpy_util as npu
import onnx_inference_manager

# Import the base inference manager
ONNXInferenceManager = onnx_inference_manager.ONNXInferenceManager

# ==================== CONFIGURATION ====================
# Depth Anything V2 (https://github.com/DepthAnything/Depth-Anything-V2), ONNX export.
# Monocular depth estimation -- a single dense per-pixel depth map for the whole frame, no
# boxes/classes/per-instance identity and therefore no ByteTracker, no table_output. Also,
# unlike onnx_rvm_seg.py (this project's other texture-in/texture-out script, and the
# closest architectural match), Depth Anything is plain frame-independent inference --
# no recurrent state carried between frames, so no IOBinding override is needed either;
# the base class's default session.run() already covers this model exactly.
#
# Only depth_anything_v2_vits_dynamic.onnx is supported; older depth models (MiDaS v2,
# DPT-BEiT, a HuggingFace rank-5 export) were dropped -- see git history if needed again.
MODEL_FILENAME = 'depth_anything_v2_vits_dynamic.onnx'

# input:  'image' [batch, 3, height, width] float32
# output: 'depth' [batch, 14*floor(height/14), 14*floor(width/14)] float32 -- the ViT
#         encoder's 14px patch size means the output can be very slightly smaller than
#         the input if height/width aren't already multiples of 14. postprocess() uses
#         the output's own shape directly rather than resizing back up.

# ImageNet mean/std, precomputed as pixel * scale + offset (equivalent to
# (pixel - mean) / std but avoids a per-element division every frame).
_INET_SCALE = np.array([1.0 / 0.229, 1.0 / 0.224, 1.0 / 0.225], dtype=np.float32)
_INET_OFFSET = np.array([-0.485 / 0.229, -0.456 / 0.224, -0.406 / 0.225], dtype=np.float32)


class DepthAnythingInference(ONNXInferenceManager):
	"""Depth Anything V2 monocular depth estimation -- single dense depth map per frame,
	no recurrent state and no tracking (see module docstring)."""

	def __init__(self):
		super().__init__()
		self._input_tensor_buf = None
		self._input_buf_shape = None
		self._output_buf = None
		self._output_buf_shape = None

	def get_model_path(self):
		"""Return path to the Depth Anything V2 model."""
		model_dir = os.path.join(project.folder, 'data', 'ml', 'depth-anything')
		return os.path.join(model_dir, MODEL_FILENAME)

	def on_model_loaded(self, session):
		"""Log model I/O -- see module docstring for the confirmed shapes."""
		outputs = session.get_outputs()
		self.printONNX(f"Depth Anything model outputs ({len(outputs)}):")
		for o in outputs:
			self.printONNX(f"  name='{o.name}' shape={o.shape} type={o.type}")
		inputs = session.get_inputs()
		for inp in inputs:
			self.printONNX(f"  input name='{inp.name}' shape={inp.shape} type={inp.type}")
		self.check_providers(session)

	def preprocess(self, nA):
		"""Preprocess input for Depth Anything V2. Input nA is float32 RGBA 0-1 from
		TouchDesigner (bottom-up). ImageNet-normalizes directly from that 0-1 range --
		no intermediate 0-255 step needed."""
		h, w = nA.shape[:2]
		num_channels = nA.shape[2] if len(nA.shape) == 3 else 1

		needed = (1, 3, h, w)
		if self._input_buf_shape != needed:
			self._input_tensor_buf = np.empty(needed, dtype=np.float32)
			self._input_buf_shape = needed

		if num_channels >= 3:
			flipped = nA[::-1, :, :3]  # flip V + drop alpha (view, no alloc)
		else:
			flipped = self.npu.grayscale_to_rgb(self.npu.flip_v(nA))

		# ImageNet normalize: pixel * scale + offset (no per-element division).
		self._input_tensor_buf[0, 0] = flipped[:, :, 0] * _INET_SCALE[0] + _INET_OFFSET[0]
		self._input_tensor_buf[0, 1] = flipped[:, :, 1] * _INET_SCALE[1] + _INET_OFFSET[1]
		self._input_tensor_buf[0, 2] = flipped[:, :, 2] * _INET_SCALE[2] + _INET_OFFSET[2]

		return self._input_tensor_buf

	def postprocess(self, outputs):
		"""Normalize the raw depth map to 0-1 and expand to RGB for TD."""
		depth = np.squeeze(outputs[0])  # (H, W)
		h, w = depth.shape[:2]

		# Normalize to 0-1 in-place (no temp array allocation).
		d_min = depth.min()
		d_range = depth.max() - d_min
		if d_range > 0:
			np.subtract(depth, d_min, out=depth)
			np.multiply(depth, 1.0 / d_range, out=depth)
		else:
			depth[:] = 0

		# Expand grayscale to RGB + flip via single broadcast assignment.
		needed = (h, w, 3)
		if self._output_buf is None or self._output_buf_shape != needed:
			self._output_buf = np.empty(needed, dtype=np.float32)
			self._output_buf_shape = needed
		self._output_buf[:] = depth[::-1, :, np.newaxis]  # flip + broadcast (H,W,1)->(H,W,3)

		return self._output_buf


# Create global instance -- shut down any PREVIOUS instance first (releases its
# GPU-resident ONNX Runtime session(s) and stops its worker thread) so a script
# reload during active development doesn't leak both -- see
# onnx_inference_manager.shutdown_and_register()'s docstring for the full
# mechanism this avoids (and why it's NOT TD's own store()/fetch(), which risked
# a real crash trying to persist a live, unpicklable manager instance).
inference_manager = DepthAnythingInference()
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
