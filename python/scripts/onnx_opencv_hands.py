import os
import math
import numpy as np
import cv2
import onnxruntime as ort

# custom util imports
import numpy as npu
import onnx_inference_manager
import object_tracker

# Import the base inference manager
ONNXInferenceManager = onnx_inference_manager.ONNXInferenceManager
ByteTracker = object_tracker.ByteTracker
_nms = object_tracker.nms
_iou_matrix = object_tracker._iou_matrix
_track_color = object_tracker.track_color

# ==================== CONFIGURATION ====================
# MediaPipe Hands (BlazePalm detector + 21-point hand landmark model), OpenCV Zoo ONNX
# exports (data/ml/opencv_zoo/) -- REPLACES the earlier Qualcomm AI Hub export
# (onnx_mediapipe_hands.py) after that export showed a severe periodic-freeze pathology;
# see docs/learnings/mediapipe-landmarks.md for the full investigation. This script uses
# an independently converted export of the same MediaPipe Hands architecture (OpenCV's own
# TFLite->ONNX conversion, not Qualcomm's) to sidestep it.
#
# Same two-stage architecture as onnx_mediapipe_face.py/onnx_mediapipe_hands.py: palm
# DETECTION runs through the normal threaded ONNXInferenceManager pipeline; per-hand
# LANDMARK inference runs synchronously on the main thread inside postprocess(), one call
# per hand (fixed batch-1 input).
#
# Important export-specific differences from the Qualcomm version:
#   - Input tensors are NHWC ([1,H,W,3]), NOT NCHW like the Qualcomm export -- simpler for
#     TD besides, since a TOP's numpyArray() is already HWC.
#   - Palm detector input is 192x192 (not 256x256), using MediaPipe's own STOCK anchor
#     config (NUM_LAYERS=4, strides=[8,16,16,16]), matching OpenCV Zoo's own reference
#     anchor table exactly -- no reverse-engineering needed here, unlike the Qualcomm
#     export's undocumented 2944-anchor grid.
#   - Landmark model input is 224x224 (MediaPipe's own stock size, not Qualcomm's 256).
#   - Landmark model output x/y is in CROP-SPACE PIXELS directly -- the OPPOSITE
#     convention from the Qualcomm export (which was normalized 0-1, see
#     docs/learnings/mediapipe-landmarks.md). Do NOT apply the same "* LANDMARK_INPUT_SIZE"
#     scaling used there.
#   - Landmark model outputs, in ONNX Runtime's own order: [landmarks, hand_confidence
#     (sigmoid already applied), handedness (sigmoid already applied), world_landmarks].
#   - ROI enlarge/shift constants are OpenCV's own tuned values (scale=3.0, shift_y=-0.4),
#     not MediaPipe's stock published values (2.6, -0.5) -- taken directly from OpenCV
#     Zoo's own mp_handpose.py reference script.
DETECTOR_MODEL_FILENAME = 'palm_detection_mediapipe_2023feb.onnx'
LANDMARK_MODEL_FILENAME = 'handpose_estimation_mediapipe_2023feb.onnx'

# ---- BlazePalm anchor generation (MediaPipe's own stock config, confirmed exact match) ----
NUM_LAYERS = 4
BASE_STRIDES = [8, 16, 16, 16]  # native to this model's 192x192 input
MIN_SCALE = 0.1484375
MAX_SCALE = 0.75
ANCHOR_OFFSET = 0.5
ASPECT_RATIOS = [1.0]
INTERPOLATED_SCALE_ASPECT_RATIO = 1.0
NUM_KEYPOINTS = 7  # wrist(0), ..., middle_finger_mcp(2), ... (only 0 and 2 used, for rotation)
DETECTOR_INPUT_SIZE = 192

# ---- Rotation-aligned ROI (for the landmark model) ----
# Same MediaPipe rotation convention as onnx_mediapipe_hands.py (wrist->middle-MCP aligned
# to the rect's local +Y axis, target_angle=90 degrees), matching OpenCV's own
# mp_handpose.py. ROI_SCALE/SHIFT_Y are OpenCV's own tuned values, not MediaPipe's stock
# 2.6/-0.5.
TARGET_ANGLE_RAD = math.pi / 2.0
ROTATION_START_KEYPOINT = 0  # wrist
ROTATION_END_KEYPOINT = 2    # middle finger MCP
SHIFT_Y = -0.4
ROI_SCALE = 3.0
LANDMARK_INPUT_SIZE = 224  # per this model's real input shape (verified via onnxruntime)
NUM_LANDMARKS = 21

# ---- Landmark-driven ROI persistence (mirrors MediaPipe's own hand-tracking pipeline) ----
# The official MediaPipe/Tasks hand tracker does NOT re-solve palm detection from scratch
# every frame for an already-tracked hand -- it derives the next frame's landmark-model ROI
# directly from the PREVIOUS frame's own 21 landmarks (wrist + middle-finger MCP for
# rotation, full landmark bounding box for position/size), and only falls back to the palm
# detector's box when that track has no usable prior landmarks (new track) or the landmark
# model's own `hand_confidence` ("presence") output drops below threshold (hand turned away/
# occluded/out of frame). We still run the palm detector every frame (needed to feed
# ByteTracker's multi-hand IoU matching and to catch newly-entering hands), but for the ROI
# fed to the landmark model we prefer this landmark-derived crop when available -- this is
# the main lever for stability at odd hand angles, since it no longer depends on BlazePalm's
# own box regression once a hand is being tracked.
PRESENCE_THRESHOLD = 0.5  # below this, distrust held landmarks -- fall back to detector ROI
LANDMARK_ROI_MARGIN = 1.6  # padding around the landmark-derived bbox (already spans the full
# hand incl. fingers, unlike the palm detector's tight palm-only box -- so this is much
# smaller than ROI_SCALE, which additionally has to grow a palm-only box out to the fingers)

# Standard MediaPipe Hands skeleton connections (index pairs into the 21 landmarks) --
# the same well-known HAND_CONNECTIONS set used across essentially every MediaPipe
# Hands-based visualization (thumb/index/middle/ring/pinky chains + palm base). Same
# "bones" convention as onnx_yolo26_pose.py's SKELETON_EDGES/table_bones -- see
# write_bones_to_table()'s docstring for the full pattern.
HAND_SKELETON_EDGES = [
	(0, 1), (1, 2), (2, 3), (3, 4),          # thumb
	(1, 5), (5, 6), (6, 7), (7, 8),          # index finger
	(5, 9), (9, 10), (10, 11), (11, 12),     # middle finger
	(9, 13), (13, 14), (14, 15), (15, 16),   # ring finger
	(13, 17), (17, 18), (18, 19), (19, 20),  # pinky
	(0, 17),                                  # palm base (wrist to pinky base)
]

# Standard MediaPipe Hands landmark names, same index order as HAND_SKELETON_EDGES above --
# feeds object_tracker.joints_row()'s 'name' column.
HAND_LANDMARK_NAMES = [
	'wrist',
	'thumb_cmc', 'thumb_mcp', 'thumb_ip', 'thumb_tip',
	'index_mcp', 'index_pip', 'index_dip', 'index_tip',
	'middle_mcp', 'middle_pip', 'middle_dip', 'middle_tip',
	'ring_mcp', 'ring_pip', 'ring_dip', 'ring_tip',
	'pinky_mcp', 'pinky_pip', 'pinky_dip', 'pinky_tip',
]

MAX_BATCH_HANDS = 8  # see onnx_mediapipe_face.py's MAX_BATCH_FACES for the fixed-size-cap reasoning
MAX_HANDS = 2  # see onnx_mediapipe_hands.py's MAX_HANDS comment -- same phantom-detection risk

CONF_THRESHOLD = 0.5
LOW_CONF_THRESHOLD = 0.3
NMS_IOU_THRESHOLD = 0.3
CENTER_DEDUP_DIST_FACTOR = 0.8  # see onnx_mediapipe_hands.py's comment on this constant
# A more lenient distance factor used ONLY when two candidates' rotation angle (wrist->
# middle-MCP vector) nearly agrees. BlazePalm can fire a smaller, higher-scoring phantom
# detection on just a hand's fingertip cluster, with its own self-consistent but wrong-scale
# keypoints, positioned too far from the real hand for CENTER_DEDUP_DIST_FACTOR alone to
# merge safely without risking merging two genuinely different real hands -- but a
# genuinely separate hand is unlikely to share the same orientation by coincidence, so
# agreement on ORIENTATION is used to license a wider merge radius, not as a criterion alone.
ANGLE_DEDUP_DIST_FACTOR = 2.0  # TRADEOFF, not free: widens the radius within which two
# GENUINELY SEPARATE real hands with similar orientation (e.g. a prayer/clasped-hands pose)
# could be incorrectly merged into one detection -- lower via the Anglededuprange par if
# false merges of real hands show up in practice.
ANGLE_DEDUP_DEG = 20.0  # max rotation-angle difference (degrees) to treat as "same orientation"
MIN_BOX_WIDTH = 0.02
MIN_BOX_HEIGHT = 0.02
TRACKER_MAX_AGE = 15
TRACKER_IOU_THRESHOLD = 0.15
TRACKER_MIN_HITS = 3
OUTPUT_SMOOTHING = 0.5
LANDMARK_INTERVAL = 1  # see onnx_mediapipe_hands.py's LANDMARK_INTERVAL comment
DRAW_BOXES = True


def _sigmoid(x):
	return 1.0 / (1.0 + np.exp(-np.clip(x, -60, 60)))


def _calculate_scale(min_scale, max_scale, stride_index, num_strides):
	if num_strides == 1:
		return (min_scale + max_scale) * 0.5
	return min_scale + (max_scale - min_scale) * stride_index / (num_strides - 1)


def _generate_anchors(input_size, strides):
	"""Faithful port of ssd_anchors_calculator.cc's GenerateAnchors() -- confirmed exact
	match against OpenCV Zoo's own hardcoded 2016-row anchor table (mp_palmdet.py's
	_load_anchors()) for this stock MediaPipe config."""
	anchors = []
	layer_id = 0
	num_strides = len(strides)
	while layer_id < NUM_LAYERS:
		anchor_heights, anchor_widths, aspect_ratios, scales = [], [], [], []
		last_same_stride_layer = layer_id
		while (last_same_stride_layer < num_strides and
				strides[last_same_stride_layer] == strides[layer_id]):
			scale = _calculate_scale(MIN_SCALE, MAX_SCALE, last_same_stride_layer, num_strides)
			for ar in ASPECT_RATIOS:
				aspect_ratios.append(ar)
				scales.append(scale)
			if INTERPOLATED_SCALE_ASPECT_RATIO > 0.0:
				scale_next = 1.0 if last_same_stride_layer == num_strides - 1 else \
					_calculate_scale(MIN_SCALE, MAX_SCALE, last_same_stride_layer + 1, num_strides)
				scales.append(np.sqrt(scale * scale_next))
				aspect_ratios.append(INTERPOLATED_SCALE_ASPECT_RATIO)
			last_same_stride_layer += 1
		for ar, sc in zip(aspect_ratios, scales):
			r = np.sqrt(ar)
			anchor_heights.append(sc / r)
			anchor_widths.append(sc * r)
		stride = strides[layer_id]
		fm = int(np.ceil(input_size / stride))
		for y in range(fm):
			for x in range(fm):
				for _ in range(len(anchor_heights)):
					anchors.append([(x + ANCHOR_OFFSET) / fm, (y + ANCHOR_OFFSET) / fm, 1.0, 1.0])
		layer_id = last_same_stride_layer
	return np.array(anchors, dtype=np.float32)


# ==================== MEDIAPIPE HAND + LANDMARK TRACKING ====================

class OpenCVHandInference(ONNXInferenceManager):
	"""MediaPipe Hands (BlazePalm + 21-point landmark model), OpenCV Zoo export -- see
	module docstring for why this replaces onnx_mediapipe_hands.py's Qualcomm-export
	version and the specific I/O differences (NHWC, pixel-space landmarks, different ROI
	constants, different output ordering)."""

	def __init__(self):
		super().__init__()
		self.opOutputTableDAT = parent().op('table_output')
		self.opJointsTableDAT = parent().op('table_joints')
		self.opBonesTableDAT = parent().op('table_bones')
		self.conf_threshold = CONF_THRESHOLD
		self.low_conf_threshold = LOW_CONF_THRESHOLD
		self.tracker = ByteTracker(
			high_thresh=CONF_THRESHOLD, low_thresh=LOW_CONF_THRESHOLD,
			match_thresh=TRACKER_IOU_THRESHOLD, track_buffer=TRACKER_MAX_AGE,
			min_hits=TRACKER_MIN_HITS,
			# Hands move fast/erratically enough that constant-velocity extrapolation
			# through even a couple of lost frames drifts the predicted box past where the
			# hand actually reappears, dropping IoU below match_thresh and spawning a new
			# track instead of reacquiring the old one -- see object_tracker.py's
			# Track.mark_lost(). Holding position steady is more reliable here than for a
			# walking person (this tracker's other callers).
			freeze_velocity_on_loss=True,
		)
		self._box_state = {}
		self._landmark_state = {}
		self._landmark_target_state = {}
		self._handedness_state = {}
		self._handedness_target_state = {}
		self._presence_state = {}
		self._landmark_frame_counter = 0
		self.tracked_objects = []
		self._input_tensor_buf = None
		self._input_buf_shape = None
		self._output_buf = None
		self._output_buf_shape = None
		self.original_h = None
		self.original_w = None
		# True (pre-square) source dimensions -- see preprocess()'s fetch and
		# _run_landmarks_batch's docstring (mirrors onnx_mediapipe_face.py's identical fix).
		self._true_w = None
		self._true_h = None
		self._anchors = None
		self._anchor_input_size = None
		self._last_frame_rgb = None
		self._landmark_session = None

	def onSetupParameters(self, scriptOp):
		"""Add OpenCVHand-specific parameters alongside base class params."""
		super().onSetupParameters(scriptOp)
		page = scriptOp.appendCustomPage('OpenCVHand')
		p = page.appendFloat('Confthreshold', label='Confidence Threshold', size=1)
		p[0].default = CONF_THRESHOLD
		p[0].min = 0.0
		p[0].max = 1.0
		p[0].clampMin = True
		p[0].clampMax = True
		p[0].help = object_tracker.par_help('Confthreshold', subject='hand', subject_plural='hands')
		scriptOp.par.Confthreshold = CONF_THRESHOLD
		p = page.appendFloat('Lowconfthreshold', label='Low Confidence Threshold (Recovery)', size=1)
		p[0].default = LOW_CONF_THRESHOLD
		p[0].min = 0.0
		p[0].max = 1.0
		p[0].clampMin = True
		p[0].clampMax = True
		p[0].help = object_tracker.par_help('Lowconfthreshold', subject='hand', subject_plural='hands')
		scriptOp.par.Lowconfthreshold = LOW_CONF_THRESHOLD
		p = page.appendFloat('Nmsiouthreshold', label='NMS IoU Threshold (Dedup)', size=1)
		p[0].default = NMS_IOU_THRESHOLD
		p[0].min = 0.0
		p[0].max = 1.0
		p[0].clampMin = True
		p[0].clampMax = True
		p[0].help = object_tracker.par_help('Nmsiouthreshold', subject='hand', subject_plural='hands')
		scriptOp.par.Nmsiouthreshold = NMS_IOU_THRESHOLD
		p = page.appendFloat('Centerdedupdist', label='Center Dedup Distance Factor', size=1)
		p[0].default = CENTER_DEDUP_DIST_FACTOR
		p[0].min = 0.0
		p[0].max = 2.0
		p[0].clampMin = True
		p[0].clampMax = False
		p[0].help = ("Merges detections whose centers are closer than this factor times the "
			"larger box's own size, run AFTER standard IoU-based NMS -- see "
			"onnx_mediapipe_hands.py's identical par for the multi-scale-anchor-duplicate "
			"reasoning this addresses.")
		scriptOp.par.Centerdedupdist = CENTER_DEDUP_DIST_FACTOR
		p = page.appendFloat('Anglededuprange', label='Orientation-Matched Dedup Range', size=1)
		p[0].default = ANGLE_DEDUP_DIST_FACTOR
		p[0].min = 0.0
		p[0].max = 3.0
		p[0].clampMin = True
		p[0].clampMax = False
		p[0].help = ("A more lenient version of Center Dedup Distance Factor, used ONLY when "
			"two detections' rotation angle (wrist->middle-MCP) nearly agrees (within "
			f"{ANGLE_DEDUP_DEG:.0f} degrees) -- catches a phantom sharing a real hand's "
			"orientation but positioned too far from it for the plain center-distance test "
			"to merge. Tradeoff: raising this also risks merging two GENUINELY SEPARATE "
			"real hands with similar orientation held close together (e.g. a prayer/"
			"clasped-hands pose) into one detection -- lower it if that starts happening.")
		scriptOp.par.Anglededuprange = ANGLE_DEDUP_DIST_FACTOR
		p = page.appendFloat('Minboxwidth', label='Min Box Width', size=1)
		p[0].default = MIN_BOX_WIDTH
		p[0].min = 0.0
		p[0].max = 0.2
		p[0].clampMin = True
		p[0].clampMax = False
		p[0].help = object_tracker.par_help('Minboxwidth')
		scriptOp.par.Minboxwidth = MIN_BOX_WIDTH
		p = page.appendFloat('Minboxheight', label='Min Box Height', size=1)
		p[0].default = MIN_BOX_HEIGHT
		p[0].min = 0.0
		p[0].max = 0.2
		p[0].clampMin = True
		p[0].clampMax = False
		p[0].help = object_tracker.par_help('Minboxheight')
		scriptOp.par.Minboxheight = MIN_BOX_HEIGHT
		p = page.appendFloat('Roiscale', label='Landmark ROI Scale', size=1)
		p[0].default = ROI_SCALE
		p[0].min = 1.0
		p[0].max = 5.0
		p[0].clampMin = True
		p[0].clampMax = False
		p[0].help = ("How much to expand the detected palm box before extracting the "
			"rotation-aligned crop fed to the landmark model. Default (3.0) is OpenCV "
			"Zoo's own tuned value for this specific export, not MediaPipe's stock 2.6.")
		scriptOp.par.Roiscale = ROI_SCALE
		p = page.appendFloat('Roishifty', label='Landmark ROI Shift Y', size=1)
		p[0].default = SHIFT_Y
		p[0].min = -1.0
		p[0].max = 1.0
		p[0].help = ("Shifts the ROI center along the rotated crop's local Y axis (as a "
			"fraction of the raw palm box height) before scaling. Default (-0.4) is "
			"OpenCV Zoo's own tuned value, not MediaPipe's stock -0.5.")
		scriptOp.par.Roishifty = SHIFT_Y
		p = page.appendFloat('Presencethreshold', label='Hand Presence Threshold (ROI Persistence)', size=1)
		p[0].default = PRESENCE_THRESHOLD
		p[0].min = 0.0
		p[0].max = 1.0
		p[0].clampMin = True
		p[0].clampMax = True
		p[0].help = ("Below this, the landmark model's own hand-presence output is "
			"distrusted and the next frame falls back to the palm detector's box for that "
			"track's crop, instead of reusing the previous frame's own landmarks.")
		scriptOp.par.Presencethreshold = PRESENCE_THRESHOLD
		p = page.appendFloat('Landmarkroimargin', label='Landmark-Derived ROI Margin', size=1)
		p[0].default = LANDMARK_ROI_MARGIN
		p[0].min = 1.0
		p[0].max = 3.0
		p[0].clampMin = True
		p[0].clampMax = False
		p[0].help = ("Padding factor around the bounding box of the previous frame's own "
			"21 landmarks, when used as the next frame's landmark-model crop instead of the "
			"palm detector's box (see Presencethreshold).")
		scriptOp.par.Landmarkroimargin = LANDMARK_ROI_MARGIN
		p = page.appendFloat('Maxhands', label='Max Hands (Top-N By Score)', size=1)
		p[0].default = MAX_HANDS
		p[0].min = 1.0
		p[0].max = 10.0
		p[0].clampMin = True
		p[0].clampMax = False
		p[0].help = ("Hard cap on how many detections are tracked/landmarked per frame -- "
			"see onnx_mediapipe_hands.py's identical par for why this is needed.")
		scriptOp.par.Maxhands = MAX_HANDS
		p = page.appendFloat('Landmarkinterval', label='Landmark Update Interval (Frames)', size=1)
		p[0].default = LANDMARK_INTERVAL
		p[0].min = 1.0
		p[0].max = 30.0
		p[0].clampMin = True
		p[0].clampMax = False
		p[0].help = ("How often (in frames) to re-run the landmark model, shared by every "
			"tracked hand at once (1 = every frame). Between updates, each hand's last "
			"reading is held.")
		scriptOp.par.Landmarkinterval = LANDMARK_INTERVAL
		p = page.appendToggle('Outputtrackdata', label='Output Track Data (Table)')
		p[0].default = True
		p[0].help = "Whether to write per-frame hand tracking + landmark data to the tables at all."
		scriptOp.par.Outputtrackdata = True
		p = page.appendFloat('Tracklossframes', label='Track Loss Frames', size=1)
		p[0].default = TRACKER_MAX_AGE
		p[0].min = 0.0
		p[0].max = 90.0
		p[0].clampMin = True
		p[0].clampMax = False
		p[0].help = object_tracker.par_help('Tracklossframes')
		scriptOp.par.Tracklossframes = TRACKER_MAX_AGE
		p = page.appendFloat('Trackiouthreshold', label='Track IoU Threshold', size=1)
		p[0].default = TRACKER_IOU_THRESHOLD
		p[0].min = 0.0
		p[0].max = 1.0
		p[0].clampMin = True
		p[0].clampMax = True
		p[0].help = object_tracker.par_help('Trackiouthreshold', subject='hand', subject_plural='hands')
		scriptOp.par.Trackiouthreshold = TRACKER_IOU_THRESHOLD
		p = page.appendFloat('Trackconfirmframes', label='Track Confirm Frames', size=1)
		p[0].default = TRACKER_MIN_HITS
		p[0].min = 1.0
		p[0].max = 30.0
		p[0].clampMin = True
		p[0].clampMax = False
		p[0].help = object_tracker.par_help('Trackconfirmframes', subject='hand', subject_plural='hands')
		scriptOp.par.Trackconfirmframes = TRACKER_MIN_HITS
		p = page.appendFloat('Outputsmoothing', label='Output Smoothing (Box + Landmarks)', size=1)
		p[0].default = OUTPUT_SMOOTHING
		p[0].min = 0.0
		p[0].max = 1.0
		p[0].clampMin = True
		p[0].clampMax = True
		p[0].help = object_tracker.par_help('Outputsmoothing', extra=(
			"Also smooths each tracked hand's 21 landmark positions frame to frame."
		))
		scriptOp.par.Outputsmoothing = OUTPUT_SMOOTHING
		p = page.appendToggle('Drawdebug', label='Draw Debug Overlay')
		p[0].default = DRAW_BOXES
		p[0].help = ("Draws hand box outlines + track id + handedness + landmark points on "
			"the output image. The main landmark visualization is the Debug COMP's geo "
			"instancing (driven by table_landmarks), not this overlay.")
		scriptOp.par.Drawdebug = DRAW_BOXES

	def get_model_path(self):
		"""Return path to the BlazePalm detector model."""
		model_dir = os.path.join(project.folder, 'data', 'ml', 'opencv_zoo')
		return os.path.join(model_dir, DETECTOR_MODEL_FILENAME)

	def on_model_loaded(self, session):
		"""Log detector I/O and load the second (unthreaded) landmark session."""
		outputs = session.get_outputs()
		self.printONNX(f"OpenCV Zoo palm detector outputs ({len(outputs)}):")
		for o in outputs:
			self.printONNX(f"  name='{o.name}' shape={o.shape} type={o.type}")
		inputs = session.get_inputs()
		for inp in inputs:
			self.printONNX(f"  input name='{inp.name}' shape={inp.shape} type={inp.type}")
		self.check_providers(session)

		landmark_path = os.path.join(project.folder, 'data', 'ml', 'opencv_zoo', LANDMARK_MODEL_FILENAME)
		self._landmark_session = ort.InferenceSession(landmark_path, providers=onnx_inference_manager.providers())
		self.printONNX(f"Hand landmark model loaded: {landmark_path}")
		self.printONNX(f"  Active providers: {self._landmark_session.get_providers()}")

	def preprocess(self, nA):
		"""Preprocess for BlazePalm. NHWC input (not NCHW like the Qualcomm export) --
		assumes TD has already resized input to a SQUARE working resolution upstream
		(fit_square_sm, 'fill' stretch)."""
		self.original_h, self.original_w = nA.shape[:2]
		num_channels = nA.shape[2] if len(nA.shape) == 3 else 1

		needed = (1, self.original_h, self.original_w, 3)
		if self._input_buf_shape != needed:
			self._input_tensor_buf = np.empty(needed, dtype=np.float32)
			self._input_buf_shape = needed

		if self._anchor_input_size != self.original_w:
			scale_factor = self.original_w / float(DETECTOR_INPUT_SIZE)
			strides = [int(round(s * scale_factor)) for s in BASE_STRIDES]
			self._anchors = _generate_anchors(self.original_w, strides)
			self._anchor_input_size = self.original_w
			self.printONNX(f"Regenerated {len(self._anchors)} anchors for {self.original_w}x{self.original_h}")

		if num_channels >= 3:
			flipped = nA[::-1, :, :3]  # flip V + drop alpha (view, no alloc)
		else:
			img = self.npu.flip_v(nA)
			flipped = self.npu.grayscale_to_rgb(img)

		self._last_frame_rgb = np.ascontiguousarray(flipped, dtype=np.float32)

		# True (pre-square) source dimensions -- see _run_landmarks_batch's docstring for
		# why the rotation-aligned crop needs these (mirrors onnx_mediapipe_face.py).
		try:
			src = self.scriptOp.parent().op('null_passthrough')
			self._true_w, self._true_h = src.width, src.height
		except Exception:
			self._true_w, self._true_h = self.original_w, self.original_h

		self._input_tensor_buf[0] = flipped

		return self._input_tensor_buf

	def postprocess(self, outputs):
		"""Decode BlazePalm detections, track hands, run rotation-aligned landmark
		inference per tracked hand."""
		if len(outputs) != 2:
			needed_shape = (self.original_h or DETECTOR_INPUT_SIZE, self.original_w or DETECTOR_INPUT_SIZE, 3)
			if self._output_buf is None or self._output_buf_shape != needed_shape:
				self._output_buf = np.zeros(needed_shape, dtype=np.float32)
				self._output_buf_shape = needed_shape
			return self.npu.flip_v(self._output_buf)

		input_w, input_h = self.original_w, self.original_h
		box_land = outputs[0][0]                    # (2016, 18)
		box_scores = _sigmoid(outputs[1][0, :, 0])   # (2016,)
		anchors = self._anchors

		self.conf_threshold = self._par_or_default('Confthreshold', CONF_THRESHOLD)
		self.low_conf_threshold = self._par_or_default('Lowconfthreshold', LOW_CONF_THRESHOLD)
		nms_iou_threshold = self._par_or_default('Nmsiouthreshold', NMS_IOU_THRESHOLD)
		center_dedup_dist = self._par_or_default('Centerdedupdist', CENTER_DEDUP_DIST_FACTOR)
		angle_dedup_dist = self._par_or_default('Anglededuprange', ANGLE_DEDUP_DIST_FACTOR)
		min_box_width = self._par_or_default('Minboxwidth', MIN_BOX_WIDTH)
		min_box_height = self._par_or_default('Minboxheight', MIN_BOX_HEIGHT)
		roi_scale = self._par_or_default('Roiscale', ROI_SCALE)
		roi_shift_y = self._par_or_default('Roishifty', SHIFT_Y)
		self.tracker.high_thresh = self.conf_threshold
		self.tracker.low_thresh = self.low_conf_threshold
		self.tracker.match_thresh = self._par_or_default('Trackiouthreshold', TRACKER_IOU_THRESHOLD)
		self.tracker.track_buffer = self._par_or_default('Tracklossframes', TRACKER_MAX_AGE)
		self.tracker.min_hits = int(self._par_or_default('Trackconfirmframes', TRACKER_MIN_HITS))
		smoothing = self._par_or_default('Outputsmoothing', OUTPUT_SMOOTHING)

		box_scale = float(input_w)
		x_raw, y_raw, w_raw, h_raw = box_land[:,0], box_land[:,1], box_land[:,2], box_land[:,3]
		x_center = x_raw / box_scale * anchors[:,2] + anchors[:,0]
		y_center = y_raw / box_scale * anchors[:,3] + anchors[:,1]
		w = w_raw / box_scale * anchors[:,2]
		h = h_raw / box_scale * anchors[:,3]
		boxes_native = np.stack([x_center - w/2, y_center - h/2, x_center + w/2, y_center + h/2], axis=-1)

		keypoints = []
		for k in range(NUM_KEYPOINTS):
			off = 4 + k * 2
			kx = box_land[:,off] / box_scale * anchors[:,2] + anchors[:,0]
			ky = box_land[:,off+1] / box_scale * anchors[:,3] + anchors[:,1]
			keypoints.append(np.stack([kx, ky], axis=-1))
		keypoints = np.stack(keypoints, axis=1)  # (2016, 7, 2), normalized, native orientation

		valid = (box_scores > self.low_conf_threshold)
		valid &= (boxes_native[:,2] - boxes_native[:,0] >= min_box_width) & (boxes_native[:,3] - boxes_native[:,1] >= min_box_height)
		boxes_native = boxes_native[valid]
		scores_valid = box_scores[valid]
		kps_valid = keypoints[valid]

		if len(boxes_native) > 0:
			keep = _nms(boxes_native, scores_valid, nms_iou_threshold)
			boxes_native = boxes_native[keep]
			scores_valid = scores_valid[keep]
			kps_valid = kps_valid[keep]

		if len(boxes_native) > 0:
			keep2 = _dedup_by_center_distance(
				boxes_native, scores_valid, center_dedup_dist,
				wrist_kps=kps_valid[:, ROTATION_START_KEYPOINT],
				mid_mcp_kps=kps_valid[:, ROTATION_END_KEYPOINT],
				angle_dist_factor=angle_dedup_dist,
			)
			boxes_native = boxes_native[keep2]
			scores_valid = scores_valid[keep2]
			kps_valid = kps_valid[keep2]

		max_hands = int(self._par_or_default('Maxhands', MAX_HANDS))

		# Drop any raw candidate this frame that's a likely phantom of an ALREADY-TRACKED
		# hand, regardless of max_hands capacity -- a capacity-gated check alone isn't
		# enough: with only ONE real hand tracked and max_hands=2, a phantom sharing that
		# hand's rough position/orientation would still slip through as a "legitimate"
		# candidate for the open slot. Mirrors the intent of MediaPipe's own
		# hand_landmark_tracking graph (which gates palm detection off entirely once enough
		# hands are tracked); we still run the detector every frame and instead apply the
		# same effective filtering per-candidate.
		#
		# Only candidates WITHOUT a strong direct IoU match to an existing track are checked
		# here -- a candidate with a strong match is very likely that track's own correct
		# per-frame update, left to ByteTracker's Hungarian association. Candidates that
		# would otherwise spawn a brand-new track are checked against the same
		# center+orientation test _dedup_by_center_distance uses, but against each track's
		# own persisted box_native/rot_keypoints_native instead of same-frame peers; a match
		# means "probably the same hand at the wrong assumed scale," so it's dropped instead
		# of spawning a competing track.
		if len(boxes_native) > 0 and self.tracker.tracks:
			track_native_boxes = [t.payload.get('box_native') for t in self.tracker.tracks]
			track_native_boxes = [b for b in track_native_boxes if b is not None]
			has_direct_iou_match = np.zeros(len(boxes_native), dtype=bool)
			if track_native_boxes:
				iou = _iou_matrix(boxes_native, np.array(track_native_boxes))
				has_direct_iou_match = iou.max(axis=1) > 0.05
			needs_check = np.where(~has_direct_iou_match)[0]
			if len(needs_check) > 0:
				redundant = _match_existing_tracks(
					boxes_native[needs_check], kps_valid[needs_check], self.tracker.tracks,
					ROTATION_START_KEYPOINT, ROTATION_END_KEYPOINT,
					center_dedup_dist, angle_dedup_dist,
				)
				keep_mask = np.ones(len(boxes_native), dtype=bool)
				keep_mask[needs_check[redundant]] = False
				boxes_native = boxes_native[keep_mask]
				scores_valid = scores_valid[keep_mask]
				kps_valid = kps_valid[keep_mask]

		if len(boxes_native) > max_hands:
			top_n = np.argsort(-scores_valid)[:max_hands]
			boxes_native = boxes_native[top_n]
			scores_valid = scores_valid[top_n]
			kps_valid = kps_valid[top_n]

		# Isotropic box-SIZE correction -- see onnx_mediapipe_face.py's identical fix and
		# docs/learnings/debug-comp-camera-aspect.md (Bug 3) for the full reasoning.
		# BlazePalm's box regression outputs w_raw==h_raw in square-buffer terms
		# (fixed_anchor_size), so naively reprojecting width by true_w and height by true_h
		# independently bakes the source frame's own aspect ratio into every box.
		box_w_sq = boxes_native[:, 2] - boxes_native[:, 0]
		box_h_sq = boxes_native[:, 3] - boxes_native[:, 1]
		box_cx_sq = (boxes_native[:, 0] + boxes_native[:, 2]) / 2
		box_cy_sq = (boxes_native[:, 1] + boxes_native[:, 3]) / 2
		true_aspect = (self._true_w or input_w) / (self._true_h or input_h)
		iso_w = box_w_sq / math.sqrt(true_aspect)
		iso_h = box_h_sq * math.sqrt(true_aspect)
		boxes_native_iso = np.stack([
			box_cx_sq - iso_w / 2, box_cy_sq - iso_h / 2,
			box_cx_sq + iso_w / 2, box_cy_sq + iso_h / 2,
		], axis=-1)

		boxes_td = boxes_native_iso.copy()
		boxes_td[:, 1], boxes_td[:, 3] = 1.0 - boxes_td[:, 3], 1.0 - boxes_td[:, 1]

		detections = []
		for i in range(len(boxes_td)):
			detections.append({
				'box': boxes_td[i].tolist(),
				'score': float(scores_valid[i]),
				'box_native': boxes_native[i].tolist(),
				'rot_keypoints_native': [kps_valid[i, ROTATION_START_KEYPOINT].tolist(),
					kps_valid[i, ROTATION_END_KEYPOINT].tolist()],
			})

		active_tracks = self.tracker.update(detections)

		confirmed = []
		for t in active_tracks:
			if t.score < self.conf_threshold or not t.confirmed:
				continue
			box = t.box
			smoothed = object_tracker.box_smooth(self._box_state, t.track_id, box, smoothing)

			box_native = t.payload.get('box_native')
			rot_keypoints_native = t.payload.get('rot_keypoints_native')
			if box_native is None or rot_keypoints_native is None:
				x1, y1_td, x2, y2_td = smoothed
				box_native = [x1, 1.0 - y2_td, x2, 1.0 - y1_td]
				rot_keypoints_native = None
			confirmed.append({
				'track': t, 'smoothed': smoothed,
				'box_native': box_native, 'rot_keypoints_native': rot_keypoints_native,
			})

		if len(confirmed) > max_hands:
			# Seniority (total_frames) beats raw freshness/lost_frames here: a briefly
			# occluded but long-tracked hand should outrank a brand-new spurious detection
			# for one of the max_hands slots -- otherwise this cap defeats Tracklossframes'
			# purpose the instant a noise detection sneaks past NMS/dedup. lost_frames/score
			# only break ties among similarly-established tracks.
			confirmed.sort(key=lambda c: (-c['track'].total_frames, c['track'].lost_frames, -c['track'].score))
			confirmed = confirmed[:max_hands]

		presence_threshold = self._par_or_default('Presencethreshold', PRESENCE_THRESHOLD)
		landmark_roi_margin = self._par_or_default('Landmarkroimargin', LANDMARK_ROI_MARGIN)
		landmark_interval = max(1, int(self._par_or_default('Landmarkinterval', LANDMARK_INTERVAL)))
		self._landmark_frame_counter += 1
		if confirmed and self._landmark_frame_counter % landmark_interval == 0:
			batch_results = self._run_landmarks_batch(
				confirmed, roi_scale, roi_shift_y, presence_threshold, landmark_roi_margin)
			for c, (landmarks, handedness, presence) in zip(confirmed, batch_results):
				track_id = c['track'].track_id
				# Raw inference TARGETS, not the displayed value -- see the per-frame
				# smoothing pass below, which is what actually produces _landmark_state/
				# _handedness_state now (updated every frame, not just inference frames).
				if landmarks is not None:
					self._landmark_target_state[track_id] = landmarks
				if handedness is not None:
					self._handedness_target_state[track_id] = handedness
				# Deliberately UNSMoothed -- this gates next frame's ROI source (see
				# _run_landmarks_batch), so it needs to react immediately when a hand turns
				# away/gets occluded rather than lag behind a fading EMA.
				if presence is not None:
					self._presence_state[track_id] = presence

		# Lerp toward the latest inference target EVERY frame, regardless of
		# Landmarkinterval -- at interval>1, the target itself only updates once every N
		# frames, but without this the DISPLAYED landmarks held completely static between
		# updates then snapped once the next inference landed, reading as stepping/stutter
		# proportional to the interval. Continuing to ease toward a fixed target on the
		# in-between frames spreads that same catch-up smoothly across them instead.
		for c in confirmed:
			track_id = c['track'].track_id
			target = self._landmark_target_state.get(track_id)
			if target is not None:
				prev = self._landmark_state.get(track_id)
				self._landmark_state[track_id] = (
					target if prev is None else prev * smoothing + target * (1.0 - smoothing)
				)
			target_h = self._handedness_target_state.get(track_id)
			if target_h is not None:
				prev_h = self._handedness_state.get(track_id)
				self._handedness_state[track_id] = (
					target_h if prev_h is None else prev_h * smoothing + target_h * (1.0 - smoothing)
				)

		self.tracked_objects = []
		for c in confirmed:
			t = c['track']
			smoothed = c['smoothed']
			held_landmarks = self._landmark_state.get(t.track_id)
			held_handedness = self._handedness_state.get(t.track_id)

			cx = (smoothed[0] + smoothed[2]) / 2
			cy = (smoothed[1] + smoothed[3]) / 2
			w = smoothed[2] - smoothed[0]
			h = smoothed[3] - smoothed[1]
			self.tracked_objects.append({
				'track_id': t.track_id,
				'score': t.score,
				'cx': cx, 'cy': cy, 'w': w, 'h': h,
				'x_left': smoothed[0],
				'x_right': smoothed[2],
				'y_top': smoothed[3],
				'y_bottom': smoothed[1],
				'vx': float(t.mean[4]), 'vy': float(t.mean[5]),
				'lost_frames': t.lost_frames,
				'total_frames': t.total_frames,
				'landmarks': held_landmarks,  # (21,3) TD-space normalized, or None
				# per this export's own confirmed convention: ~1.0 = Right hand, ~0.0 = Left
				'handedness': 'Right' if (held_handedness is not None and held_handedness > 0.5) else
					('Left' if held_handedness is not None else None),
			})

		active_ids = {t.track_id for t in active_tracks}
		object_tracker.prune_stale(
			active_ids, self._box_state, self._landmark_state, self._landmark_target_state,
			self._handedness_state, self._handedness_target_state, self._presence_state,
		)

		if DRAW_BOXES:
			output_img = self.npu.flip_v(self.draw_tracked_hands())
		else:
			# Black frame -- no need to allocate/draw/flip/color-convert every frame when
			# the overlay is off, just reuse a static cached buffer (same pattern as the
			# no-detector-output-yet branch above, and every other onnx_*.py script's
			# Drawdebug handling). The REAL landmark visualization is the Debug COMP's geo
			# instancing driven by table_landmarks, unaffected by this toggle either way.
			needed_shape = (self.original_h or DETECTOR_INPUT_SIZE, self.original_w or DETECTOR_INPUT_SIZE, 3)
			if self._output_buf is None or self._output_buf_shape != needed_shape:
				self._output_buf = np.zeros(needed_shape, dtype=np.float32)
				self._output_buf_shape = needed_shape
			output_img = self._output_buf
		return output_img

	def on_result_published(self):
		"""Flush table_output/table_landmarks/table_bones from tracked_objects right
		after this frame's texture publishes, before the next frame's capture/dispatch
		-- see ONNXInferenceManager.on_result_published()'s docstring. Gated by
		Outputtrackdata, same reasoning as onnx_yolo26_seg.py's identical method."""
		if self._par_or_default('Outputtrackdata', True):
			self.write_tracks_to_table()
			self.write_landmarks_to_table()
			self.write_bones_to_table()

	def _run_landmarks_batch(self, confirmed, roi_scale, roi_shift_y, presence_threshold, landmark_roi_margin):
		"""Extract each confirmed hand's own rotation-aligned crop and run the landmark
		model once per hand (fixed batch-1 NHWC input). Returns a list of
		(landmarks_or_None, handedness_or_None, presence_or_None) tuples, same length as
		`confirmed`.

		Each hand's crop ROI (center/size/rotation) comes from one of two sources: the
		fresh palm-detector box (`box_native`/`rot_keypoints_native`, as before), OR --
		when that track has a trusted previous landmark result (presence >=
		presence_threshold) -- an ROI derived directly from THOSE landmarks (wrist +
		middle-MCP for rotation, full 21-point bbox for position/size), bypassing the
		detector's box entirely. See PRESENCE_THRESHOLD/LANDMARK_ROI_MARGIN's module-level
		comment for why.

		Works in TRUE (pre-square) pixel units for the rotation/scale/center math, not the
		square working buffer's own pixel units -- see onnx_mediapipe_face.py's identical
		method and docs/learnings/debug-comp-camera-aspect.md (Bug 3) for the full
		reasoning. `fit_square_sm`'s 'fill' stretch preserves axis-aligned POSITION
		fractions exactly, but not SIZE (this detector's box regression outputs
		width_fraction == height_fraction in square-space) or ROTATION (rotating within an
		anisotropically-stretched pixel grid introduces real shear) -- both need
		correcting against the true, undistorted frame.
		"""
		results = [(None, None, None)] * len(confirmed)
		frame = self._last_frame_rgb
		if frame is None or self._landmark_session is None or not confirmed:
			return results
		square_h, square_w = frame.shape[:2]
		true_w = self._true_w or square_w
		true_h = self._true_h or square_h
		dx_factor = true_w / square_w
		dy_factor = true_h / square_h
		true_aspect = true_w / true_h
		iso_sqrt_aspect = math.sqrt(true_aspect)

		if len(confirmed) > MAX_BATCH_HANDS:
			self.printONNX(
				f"WARNING: {len(confirmed)} hands this frame exceeds MAX_BATCH_HANDS="
				f"{MAX_BATCH_HANDS} -- landmarking only the first {MAX_BATCH_HANDS}."
			)

		for i, c in enumerate(confirmed[:MAX_BATCH_HANDS]):
			track_id = c['track'].track_id
			held_lm = self._landmark_state.get(track_id)
			held_presence = self._presence_state.get(track_id)
			use_landmark_roi = held_lm is not None and held_presence is not None and held_presence >= presence_threshold

			if use_landmark_roi:
				# Derive the crop directly from the PREVIOUS frame's own 21 landmarks
				# (already TRUE-space normalized, TD y-flipped -- see write path below)
				# instead of the fresh palm-detector box. No roi_shift_y offset here: unlike
				# the palm detector's palm-only box, this bbox already spans the whole hand.
				lm_x = held_lm[:, 0] * true_w
				lm_y = (1.0 - held_lm[:, 1]) * true_h
				min_x, max_x = float(lm_x.min()), float(lm_x.max())
				min_y, max_y = float(lm_y.min()), float(lm_y.max())
				box_cx, box_cy = (min_x + max_x) / 2.0, (min_y + max_y) / 2.0
				box_w = (max_x - min_x) * landmark_roi_margin
				box_h = (max_y - min_y) * landmark_roi_margin
				if box_w <= 0 or box_h <= 0:
					continue
				dx = lm_x[9] - lm_x[0]  # middle_finger_mcp - wrist
				dy = lm_y[9] - lm_y[0]
				angle_rad = TARGET_ANGLE_RAD - math.atan2(-dy, dx)
				side = max(box_w, box_h)
			else:
				box_native = c['box_native']
				rot_keypoints_native = c['rot_keypoints_native']
				# box_native is a normalized SQUARE-space fraction; fraction-of-square ==
				# fraction-of-true for plain axis-aligned POSITION (see docstring), so the
				# center is correct as-is. SIZE needs the isotropic correction (see docstring).
				x1, y1, x2, y2 = box_native[0]*true_w, box_native[1]*true_h, box_native[2]*true_w, box_native[3]*true_h
				box_cx, box_cy = (x1+x2)/2, (y1+y2)/2
				box_w_sq_frac = box_native[2] - box_native[0]
				box_h_sq_frac = box_native[3] - box_native[1]
				box_w = box_w_sq_frac * true_w / iso_sqrt_aspect
				box_h = box_h_sq_frac * true_h * iso_sqrt_aspect
				if box_w <= 0 or box_h <= 0:
					continue

				if rot_keypoints_native is not None:
					wrist, middle_mcp = rot_keypoints_native
					dx = (middle_mcp[0] - wrist[0]) * true_w
					dy = (middle_mcp[1] - wrist[1]) * true_h
					angle_rad = TARGET_ANGLE_RAD - math.atan2(-dy, dx)
				else:
					angle_rad = 0.0

				shift_x_px = -box_h * roi_shift_y * math.sin(angle_rad)
				shift_y_px = box_h * roi_shift_y * math.cos(angle_rad)
				box_cx += shift_x_px
				box_cy += shift_y_px

				side = max(box_w, box_h) * roi_scale
			scale = LANDMARK_INPUT_SIZE / side
			cos_a, sin_a = math.cos(-angle_rad), math.sin(-angle_rad)
			R = np.array([[cos_a, -sin_a], [sin_a, cos_a]], dtype=np.float64)
			D = np.array([[dx_factor, 0.0], [0.0, dy_factor]], dtype=np.float64)
			# A operates directly on SQUARE-pixel input (D converts to true-pixel-
			# equivalent first, then the correct TRUE-space rotation+scale applies).
			A = scale * R @ D
			center_out = LANDMARK_INPUT_SIZE / 2
			center_true = np.array([box_cx, box_cy])
			t_vec = np.array([center_out, center_out]) - scale * R @ center_true
			M = np.hstack([A, t_vec.reshape(2, 1)]).astype(np.float32)

			aligned = cv2.warpAffine(frame, M, (LANDMARK_INPUT_SIZE, LANDMARK_INPUT_SIZE), flags=cv2.INTER_LINEAR)
			nhwc = aligned.astype(np.float32)[np.newaxis, ...]  # (1,224,224,3)

			A_inv = np.linalg.inv(A)
			t_inv = -A_inv @ t_vec

			lmk_out = self._landmark_session.run(None, {'input_1': nhwc})
			# outputs, in ONNX Runtime's own order (confirmed via graph trace, see module
			# docstring): landmarks, hand_confidence, handedness, world_landmarks
			lm = lmk_out[0].reshape(NUM_LANDMARKS, 3)  # x/y already in CROP-SPACE PIXELS -- do NOT rescale
			handedness_raw = float(lmk_out[2][0][0])
			presence_raw = float(lmk_out[1][0][0])  # "hand_confidence" -- sigmoid already applied

			xy_crop = lm[:, :2]  # already pixel-space, unlike the Qualcomm export
			# A_inv maps crop-space pixels back to SQUARE-pixel space (A operates on
			# square-pixel input) -- must go back through D before normalizing, since
			# square-pixel position isn't fraction-equivalent to true-pixel position for
			# a point that went through the rotation step.
			square_xy = (A_inv @ xy_crop.T).T + t_inv
			true_xy = square_xy * np.array([dx_factor, dy_factor])
			x_norm = true_xy[:, 0] / true_w
			y_norm_native = true_xy[:, 1] / true_h
			y_norm_td = 1.0 - y_norm_native
			z_norm = lm[:, 2]
			landmarks = np.stack([x_norm, y_norm_td, z_norm], axis=-1).astype(np.float32)
			results[i] = (landmarks, handedness_raw, presence_raw)

		return results

	def draw_tracked_hands(self):
		"""Lightweight debug view -- box outlines + track id + handedness + landmark
		points. The main landmark visualization is the Debug COMP's geo instancing
		driven by table_landmarks. Gated entirely behind DRAW_BOXES at the
		postprocess() call site (skipped, not just drawn empty, when off); this method
		itself always draws."""
		proto_h, proto_w = self.original_h or DETECTOR_INPUT_SIZE, self.original_w or DETECTOR_INPUT_SIZE
		draw_img = np.zeros((proto_h, proto_w, 3), dtype=np.uint8)

		def to_px(td_x, td_y):
			return object_tracker.td_to_px(td_x, td_y, proto_w, proto_h)

		for obj in self.tracked_objects:
			if obj['lost_frames'] > 0 and obj['score'] < self.conf_threshold * 0.5:
				continue
			px1, py_bottom = to_px(obj['x_left'], obj['y_bottom'])
			px2, py_top = to_px(obj['x_right'], obj['y_top'])
			color_f = _track_color(obj['track_id'])
			color_bgr = (int(color_f[2]*255), int(color_f[1]*255), int(color_f[0]*255))
			if obj['lost_frames'] > 0:
				fade = object_tracker.track_fade(obj['lost_frames'], self.tracker.track_buffer)
				color_bgr = tuple(int(c * fade) for c in color_bgr)
			cv2.rectangle(draw_img, (px1, py_top), (px2, py_bottom), color_bgr, 2)
			label = f"#{obj['track_id']}"
			if obj['handedness']:
				label += f" {obj['handedness']}"
			cv2.putText(draw_img, label, (px1, max(py_top - 6, 12)),
				cv2.FONT_HERSHEY_SIMPLEX, 0.5, color_bgr, 1, cv2.LINE_AA)
			if obj['landmarks'] is not None:
				for lx, ly, _ in obj['landmarks']:
					px, py = to_px(lx, ly)
					if 0 <= px < proto_w and 0 <= py < proto_h:
						draw_img[py, px] = color_bgr

		return cv2.cvtColor(draw_img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0

	def write_tracks_to_table(self):
		"""Per-track summary Table DAT (one row per tracked hand)."""
		tbl = self.opOutputTableDAT
		if tbl is None:
			return
		tbl.clear()
		tbl.appendRow([
			*object_tracker.label_header(),
			*object_tracker.box_header(),
			'handedness',
			*object_tracker.color_header(),
		])
		for obj in self.tracked_objects:
			tbl.appendRow([
				*object_tracker.label_row(obj['track_id'], obj['score']),
				*object_tracker.box_row(obj),
				obj['handedness'] or '',
				*object_tracker.color_row(obj['track_id']),
			])

	def write_landmarks_to_table(self):
		"""Flat per-visible-landmark Table DAT, one row per landmark across ALL tracked
		hands -- shared table_joints schema, see object_tracker.joints_header()'s
		docstring. No per-landmark confidence exists for hand landmarks, so conf is a
		constant 1.0 stand-in (same reasoning as the bones conf below)."""
		tbl = self.opJointsTableDAT
		if tbl is None:
			return
		tbl.clear()
		tbl.appendRow(object_tracker.joints_header())
		for obj in self.tracked_objects:
			if obj['landmarks'] is None:
				continue
			track_id = obj['track_id']
			for name, (lx, ly, lz) in zip(HAND_LANDMARK_NAMES, obj['landmarks']):
				tbl.appendRow(object_tracker.joints_row(track_id, name, lx, ly, lz, 1.0))

	def write_bones_to_table(self):
		"""Flat per-visible-bone Table DAT, one row per skeleton connection across ALL
		tracked hands -- shared table_bones schema, see object_tracker.bones_header()'s
		docstring. Bone midpoint/angle/length computed from the landmark pairs, meant to
		drive a Debug COMP's geo instancing the exact same way as onnx_yolo26_pose.py:
		a thin unit-length rectangle, instancetx/ty=bx/by, instancerz=bangle,
		instancesx=blen. 2D only (x/y), same as the pose version -- z isn't used for the
		bone's own geometry, only for the point cloud. No per-landmark confidence exists
		for hand landmarks (unlike YOLO pose's keypoints_visible), so every bone for a
		hand with landmarks is drawn -- no per-bone visibility gating needed, and the
		shared 'conf' column carries this hand's whole-track detection score instead of
		a true per-bone value."""
		tbl = self.opBonesTableDAT
		if tbl is None:
			return
		tbl.clear()
		tbl.appendRow(object_tracker.bones_header())
		for obj in self.tracked_objects:
			if obj['landmarks'] is None:
				continue
			track_id = obj['track_id']
			lm = obj['landmarks']
			for a, b in HAND_SKELETON_EDGES:
				ax, ay, _ = lm[a]
				bx2, by2, _ = lm[b]
				dx = bx2 - ax
				dy = by2 - ay
				mx = (ax + bx2) / 2.0
				my = (ay + by2) / 2.0
				angle = math.degrees(math.atan2(dy, dx))
				length = math.hypot(dx, dy)
				tbl.appendRow(object_tracker.bones_row(track_id, mx, my, angle, length, obj['score']))


def _match_existing_tracks(boxes, kps, tracks, wrist_idx, mid_mcp_idx, dist_factor, angle_dist_factor):
	"""Boolean keep-mask: True for each candidate detection that plausibly belongs to one
	of `tracks` (by the same center+orientation test as _dedup_by_center_distance, just
	comparing against each track's own persisted box_native/rot_keypoints_native payload
	instead of same-frame peers). See the call site in postprocess() -- this stops a
	phantom from spawning a brand-new competing track once already at max_hands, for cases
	the same-frame dedup pass doesn't catch (some phantom/real pairs sit too far apart for
	any single fixed dedup radius to safely cover without risking merging two genuinely
	separate real hands, but still shouldn't get a new track when there's no open slot)."""
	track_centers, track_sizes, track_angles = [], [], []
	for t in tracks:
		tb = t.payload.get('box_native')
		if tb is None:
			continue
		track_centers.append([(tb[0] + tb[2]) / 2, (tb[1] + tb[3]) / 2])
		track_sizes.append(max(tb[2] - tb[0], tb[3] - tb[1]))
		trk = t.payload.get('rot_keypoints_native')
		if trk is not None:
			wrist, mid = trk
			track_angles.append(math.degrees(math.atan2(mid[1] - wrist[1], mid[0] - wrist[0])))
		else:
			track_angles.append(None)
	if not track_centers:
		return np.ones(len(boxes), dtype=bool)

	cand_centers = np.stack([(boxes[:, 0] + boxes[:, 2]) / 2, (boxes[:, 1] + boxes[:, 3]) / 2], axis=-1)
	cand_sizes = np.maximum(boxes[:, 2] - boxes[:, 0], boxes[:, 3] - boxes[:, 1])
	cand_wrist, cand_mid = kps[:, wrist_idx], kps[:, mid_mcp_idx]
	cand_angles = np.degrees(np.arctan2(cand_mid[:, 1] - cand_wrist[:, 1], cand_mid[:, 0] - cand_wrist[:, 0]))

	keep_mask = np.zeros(len(boxes), dtype=bool)
	for ti, t_center in enumerate(track_centers):
		dists = np.linalg.norm(cand_centers - np.array(t_center), axis=1)
		pair_size = np.maximum(cand_sizes, track_sizes[ti])
		close = dists < dist_factor * pair_size
		if track_angles[ti] is not None:
			angle_diff = np.abs(((cand_angles - track_angles[ti] + 180.0) % 360.0) - 180.0)
			close |= (angle_diff < ANGLE_DEDUP_DEG) & (dists < angle_dist_factor * pair_size)
		keep_mask |= close
	return keep_mask


def _dedup_by_center_distance(boxes, scores, dist_factor, wrist_kps=None, mid_mcp_kps=None, angle_dist_factor=None):
	"""See onnx_mediapipe_hands.py's identical helper -- second dedup pass after standard
	IoU NMS, for same-object multi-scale-anchor duplicates IoU alone can miss.

	Suppression radius uses max(kept_size, candidate_size), NOT just the currently-kept
	box's own size: a small phantom (e.g. a tight crop around just the fingertips) can
	score higher than the real, larger hand box, and using only the kept box's own size
	would give a suppression radius too small to reach the real hand's center. Standard
	IoU-based NMS doesn't catch this either, since IoU between a small nested box and a
	large containing box is naturally low regardless of score ordering. Using the pair's
	max size makes this symmetric, independent of which one scored higher.

	When wrist_kps/mid_mcp_kps/angle_dist_factor are supplied, a pair whose rotation angle
	(wrist->middle-MCP vector) agrees within ANGLE_DEDUP_DEG is ALSO merged if within the
	more lenient angle_dist_factor radius: some phantoms share a real hand's orientation
	without sharing its center or keypoints, and orientation agreement alone licenses the
	wider radius rather than being used as a merge criterion by itself.

	Clusters same-object candidates by processing in descending-score order (a box only
	seeds a NEW cluster if it isn't already claimed by an earlier, higher-scoring seed's
	radius), but the cluster's SURVIVING representative is whichever member has the LARGEST
	box, not whichever seeded the cluster -- score correlates with "looks like a confident
	hand crop," not with correctly capturing the hand's true extent, so picking the largest
	member is a better proxy for correctness than picking the highest-scoring one.
	"""
	if len(boxes) == 0:
		return []
	order = np.argsort(-scores)
	centers = np.stack([(boxes[:, 0] + boxes[:, 2]) / 2, (boxes[:, 1] + boxes[:, 3]) / 2], axis=-1)
	sizes = np.maximum(boxes[:, 2] - boxes[:, 0], boxes[:, 3] - boxes[:, 1])
	angles = None
	if wrist_kps is not None and mid_mcp_kps is not None and angle_dist_factor is not None:
		dx = mid_mcp_kps[:, 0] - wrist_kps[:, 0]
		dy = mid_mcp_kps[:, 1] - wrist_kps[:, 1]
		angles = np.degrees(np.arctan2(dy, dx))
	assigned = np.full(len(boxes), -1, dtype=int)
	next_cluster = 0
	for i in order:
		if assigned[i] != -1:
			continue
		cluster_id = next_cluster
		next_cluster += 1
		assigned[i] = cluster_id
		dists = np.linalg.norm(centers - centers[i], axis=1)
		pair_size = np.maximum(sizes[i], sizes)
		close = dists < dist_factor * pair_size
		if angles is not None:
			angle_diff = np.abs(((angles - angles[i] + 180.0) % 360.0) - 180.0)
			close |= (angle_diff < ANGLE_DEDUP_DEG) & (dists < angle_dist_factor * pair_size)
		close[i] = False
		joinable = close & (assigned == -1)
		assigned[joinable] = cluster_id
	keep = []
	for c in range(next_cluster):
		members = np.where(assigned == c)[0]
		keep.append(int(members[np.argmax(sizes[members])]))
	return keep


# Create global instance -- shut down any PREVIOUS instance first (releases its
# GPU-resident ONNX Runtime session(s) and stops its worker thread) so a script
# reload during active development doesn't leak both -- see
# onnx_inference_manager.shutdown_and_register()'s docstring for the full
# mechanism this avoids (and why it's NOT TD's own store()/fetch(), which risked
# a real crash trying to persist a live, unpicklable manager instance).
inference_manager = OpenCVHandInference()
onnx_inference_manager.shutdown_and_register(parent().path, inference_manager)

# TouchDesigner callback wrappers that delegate to the manager
def onSetupParameters(scriptOp):
	return inference_manager.onSetupParameters(scriptOp)


def onPulse(par):
	return inference_manager.onPulse(par)


def onCook(scriptOp):
	inference_manager.onCook(scriptOp)

	# Same module-level Drawdebug pattern as onnx_yolo26_pose.py/onnx_yolo26_obj_det.py/
	# onnx_yolo26_seg.py -- read on main thread here rather than via self._par_or_default()
	# inside postprocess().
	global DRAW_BOXES
	DRAW_BOXES = parent().par.Drawdebug.eval() == 1

	# Table writes happen inside inference_manager.onCook(scriptOp) above now, via
	# on_result_published() (still gated by Outputtrackdata internally).


def onGetCookLevel(scriptOp: scriptCHOP) -> CookLevel:
	return CookLevel.ALWAYS
