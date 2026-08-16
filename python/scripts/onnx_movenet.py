import os
import math
import numpy as np
import cv2

# custom util imports
import numpy as npu
import onnx_inference_manager
import object_tracker

# Import the base inference manager
ONNXInferenceManager = onnx_inference_manager.ONNXInferenceManager
KeypointTracker = object_tracker.KeypointTracker

# ==================== MODEL OUTPUT FORMAT ====================
# movenet-multipose-lightning.onnx (Google's TF Lite export):
#   input:  'input' (1, H, W, 3) INT32, plain 0-255 pixel values, NHWC -- NOT the NCHW
#           float32 (optionally ImageNet-normalized) tensor every other script in this
#           project builds. No resizing done here; assumes TD has already resized
#           input upstream (fit_square_sm), same convention as every other model.
#   output: 'output_0' (1, 6, 56) float32 -- 6 FIXED candidate person slots (unlike
#           YOLO26/RF-DETR, this is not sorted-by-confidence and has no built-in NMS).
#           A box-IoU NMS pass was tried and removed -- redundant with, and less
#           reliable than, KeypointTracker's own keypoint-distance duplicate
#           suppression (see that class's docstring).
#   Per-candidate row layout (56 values):
#     [0:51]  17 keypoints x (y, x, score) triples -- NOTE y-before-x, unlike every
#             other model in this project (x, y, conf) -- reordered in postprocess().
#     [51:55] box (ymin, xmin, ymax, xmax) -- MoveNet's own bounding box, derived
#             internally from keypoint extents, not a separately learned regression
#             (unlike YOLO/RF-DETR/YuNet's box head) -- reordered to xyxy below.
#     [55]    overall person confidence.
#
# Ported from tox/haxlib/ml/onnx/MovenetONNX.py, an older script predating this
# project's shared ONNXInferenceManager conventions. Uses object_tracker.KeypointTracker
# (keypoint-distance matching) instead of ByteTracker (box-IoU matching, used by every
# other model here) because MoveNet's box is DERIVED from keypoint extents rather than
# independently learned, so a flailing limb can swing box size/position around enough
# to make box-IoU matching noisy -- see KeypointTracker's docstring for the full
# rationale. See Round 9 in td-threaded-inference-optimization.md for the detailed
# comparison investigation against the legacy script.
KEYPOINT_NAMES = [
	'nose', 'left_eye', 'right_eye', 'left_ear', 'right_ear',
	'left_shoulder', 'right_shoulder', 'left_elbow', 'right_elbow',
	'left_wrist', 'right_wrist', 'left_hip', 'right_hip',
	'left_knee', 'right_knee', 'left_ankle', 'right_ankle',
	# Computed (not part of the model's own 17): extends past the wrist along the
	# elbow->wrist direction, same as the old script's Skeleton.setFromKeypoints() --
	# useful as a rough fingertip/hand-center proxy without a dedicated hand model.
	'left_hand', 'right_hand',
]
NUM_MODEL_KEYPOINTS = 17  # the model's own keypoints; left_hand/right_hand are computed
NUM_KEYPOINTS = len(KEYPOINT_NAMES)  # 19

# Keypoint indices used for KeypointTracker's matching distance -- the STABLE core
# (face, shoulders, hips), excluding elbows/wrists/knees/ankles/hands, which move the
# most frame-to-frame and carry the most jitter. Same exclusion set as the old script's
# Skeleton.DISTANCE_KEYPOINT_INDICES, kept as a keyword filter (not a hardcoded index
# list) so it stays correct if KEYPOINT_NAMES above ever changes.
_UNSTABLE_KEYPOINT_KEYWORDS = ('elbow', 'wrist', 'knee', 'ankle', 'hand')
DISTANCE_KEYPOINT_INDICES = [
	i for i, name in enumerate(KEYPOINT_NAMES)
	if not any(kw in name for kw in _UNSTABLE_KEYPOINT_KEYWORDS)
]

# COCO-17 skeleton edges (index pairs into KEYPOINT_NAMES) -- identical to
# onnx_yolo26_pose.py's SKELETON_EDGES for the shared 0-16 range (same COCO-17 layout
# and naming), plus two extra edges continuing each arm out to the computed hand point.
SKELETON_EDGES = [
	(0, 1), (0, 2), (1, 3), (2, 4),          # face
	(0, 5), (0, 6), (5, 6),                  # shoulders/neck
	(5, 7), (7, 9), (6, 8), (8, 10),         # arms
	(5, 11), (6, 12), (11, 12),              # torso
	(11, 13), (13, 15), (12, 14), (14, 16),  # legs
	(9, 17), (10, 18),                       # wrist -> computed hand
]

# How far past the wrist to extend the computed hand point, as a fraction of the
# elbow->wrist segment length. Matches the old script's extension_factor exactly.
HAND_EXTENSION = 0.45

# ==================== CONFIGURATION ====================
MODEL_FILENAME = 'movenet-multipose-lightning.onnx'

# Confidence threshold for a detected person to be shown/tracked (0.0 - 1.0). MoveNet's
# real person-confidence signal for this scene sits in a genuinely low band -- raising
# this at all starts dropping real, well-tracked poses -- so this is tuned against the
# observed distribution rather than a documentation-typical value, same approach as
# onnx_yolo26_pose.py's CONF_THRESHOLD.
CONF_THRESHOLD = 0.1

# Tracker: max frames to keep a lost track alive.
TRACKER_MAX_AGE = 15

# Tracker: total matched frames a brand-new track needs before it's confirmed and
# shown/output at all. See onnx_yolo26_pose.py's identical constant for the tradeoff.
TRACKER_MIN_HITS = 3

# Tracker: max summed keypoint distance (object_tracker.KeypointTracker, restricted to
# DISTANCE_KEYPOINT_INDICES above) to accept a match between a track and a detection --
# NOT a box IoU threshold (see module docstring for why this model uses KeypointTracker
# instead of ByteTracker). Coordinates are normalized 0-1, summed across ~9 stable
# keypoints -- this is an initial starting value, tune live against Maxmatchdist's par
# help.
MAX_MATCH_DIST = 0.5

# Fraction of MAX_MATCH_DIST used as the duplicate-detection suppression threshold --
# see KeypointTracker.update()'s comment for why this needs to be tighter than the
# match threshold itself.
DUP_DIST_FACTOR = 0.5

# Minimum box width/height (normalized 0-1) for a detection to be kept at all --
# see onnx_yolo26_pose.py's identical constants for why these are separate, not shared.
MIN_BOX_WIDTH = 0.05
MIN_BOX_HEIGHT = 0.05

# Smoothing factor for keypoint position lerp (0 = no smoothing, 1 = frozen). Box
# position is simply held at its last-matched value by KeypointTracker (no Kalman
# filter -- see object_tracker.py's KeypointTrack docstring), so unlike
# onnx_yolo26_pose.py this smoothing is the ONLY damping applied to position at all.
OUTPUT_SMOOTHING = 0.4

# Draw skeletons on the output image?
DRAW_BOXES = False

PERSON_BOX_COLOR_BGR = (0, 255, 0)      # Green
SKELETON_COLOR_BGR = (0, 255, 255)      # Yellow
KEYPOINT_COLOR_BGR = (0, 128, 255)      # Orange


# ==================== MOVENET MULTIPOSE ESTIMATION ====================

class MoveNetPoseInference(ONNXInferenceManager):
	"""MoveNet Multipose Lightning inference with temporal tracking.

	Architecturally close to onnx_yolo26_pose.py (see that class's docstring for the
	general split between the tracker and per-model keypoint smoothing/hysteresis) --
	the real differences are the model's own NHWC int32 input (see preprocess()), its
	(y, x, score) keypoint / (ymin, xmin, ymax, xmax) box layout (see postprocess()),
	both reordered to this project's standard (x, y, conf) / xyxy conventions
	immediately on decode, and the TRACKER itself: object_tracker.KeypointTracker
	(keypoint-distance matching) instead of ByteTracker (box-IoU matching) -- see
	object_tracker.py's "POSE-SPECIFIC TRACKER" section docstring for why. Everything
	downstream of the tracker (smoothing, table output) is identical to every other
	pose script regardless of which tracker produced the tracks.
	"""

	def __init__(self):
		super().__init__()
		self.opOutputTableDAT = parent().op('table_output')
		self.opJointsTableDAT = parent().op('table_joints')
		self.opBonesTableDAT = parent().op('table_bones')
		self.conf_threshold = CONF_THRESHOLD       # Will be overridden by custom par
		self.tracker = KeypointTracker(
			max_match_dist=MAX_MATCH_DIST, distance_keypoint_indices=DISTANCE_KEYPOINT_INDICES,
			dup_dist_factor=DUP_DIST_FACTOR, track_buffer=TRACKER_MAX_AGE,
			min_hits=TRACKER_MIN_HITS,
		)
		# Per-track keypoint smoothing/hysteresis state, keyed by track_id (see class docstring).
		self._kpt_state = {}
		# Structured tracking data exposed for CHOP/table consumption
		self.tracked_objects = []
		# Pre-allocated buffers (lazily sized)
		self._output_buf = None
		self._output_buf_shape = None
		self._input_tensor_buf = None   # pre-allocated NHWC int32 input buffer
		self._input_buf_shape = None

	def onSetupParameters(self, scriptOp):
		"""Add MoveNet-specific parameters alongside base class params -- identical
		parameter SET to onnx_yolo26_pose.py's (this comp was cloned from it) so the two
		models' tracking behavior can be tuned/compared apples-to-apples."""
		super().onSetupParameters(scriptOp)
		page = scriptOp.appendCustomPage('MoveNet')
		p: Page = page.appendFloat('Confthreshold', label='Confidence Threshold', size=1)
		p[0].default = CONF_THRESHOLD
		p[0].min = 0.0
		p[0].max = 1.0
		p[0].clampMin = True
		p[0].clampMax = True
		p[0].help = ("Minimum detection confidence for a person to be admitted to the tracker at all, "
			"and to stay displayed once tracked (KeypointTracker has no ByteTrack-style two-stage "
			"high/low recovery band -- ages out purely via Track Loss Frames/score decay instead).")
		scriptOp.par.Confthreshold = CONF_THRESHOLD
		p = page.appendFloat('Outputsmoothing', label='Output Smoothing', size=1)
		p[0].default = OUTPUT_SMOOTHING
		p[0].min = 0.0
		p[0].max = 1.0
		p[0].clampMin = True
		p[0].clampMax = True
		p[0].help = object_tracker.par_help('Outputsmoothing', what='keypoint position')
		scriptOp.par.Outputsmoothing = OUTPUT_SMOOTHING
		p = page.appendFloat('Tracklossframes', label='Track Loss Frames', size=1)
		p[0].default = TRACKER_MAX_AGE
		p[0].min = 0.0
		p[0].max = 90.0
		p[0].clampMin = True
		p[0].clampMax = False
		p[0].help = object_tracker.par_help('Tracklossframes')
		scriptOp.par.Tracklossframes = TRACKER_MAX_AGE
		p = page.appendFloat('Maxmatchdist', label='Max Match Distance', size=1)
		p[0].default = MAX_MATCH_DIST
		p[0].min = 0.0
		p[0].max = 2.0  # summed across ~9 stable keypoints -- can meaningfully exceed 1.0
		p[0].clampMin = True
		p[0].clampMax = False
		p[0].help = object_tracker.par_help('Maxmatchdist', subject='person')
		scriptOp.par.Maxmatchdist = MAX_MATCH_DIST
		p = page.appendFloat('Trackconfirmframes', label='Track Confirm Frames', size=1)
		p[0].default = TRACKER_MIN_HITS
		p[0].min = 1.0
		p[0].max = 30.0
		p[0].clampMin = True
		p[0].clampMax = False
		p[0].help = object_tracker.par_help('Trackconfirmframes', subject='person')
		scriptOp.par.Trackconfirmframes = TRACKER_MIN_HITS
		p = page.appendFloat('Minboxwidth', label='Min Box Width', size=1)
		p[0].default = MIN_BOX_WIDTH
		p[0].min = 0.0
		p[0].max = 0.2
		p[0].clampMin = True
		p[0].clampMax = False
		p[0].help = object_tracker.par_help('Minboxwidth', shape_note=(
			"a standing person is naturally much narrower than tall, so one shared threshold high "
			"enough to reject noise ends up rejecting real, legitimately tall-but-narrow people."
		))
		scriptOp.par.Minboxwidth = MIN_BOX_WIDTH
		p = page.appendFloat('Minboxheight', label='Min Box Height', size=1)
		p[0].default = MIN_BOX_HEIGHT
		p[0].min = 0.0
		p[0].max = 0.2
		p[0].clampMin = True
		p[0].clampMax = False
		p[0].help = object_tracker.par_help('Minboxheight')
		scriptOp.par.Minboxheight = MIN_BOX_HEIGHT
		p = page.appendToggle('Drawcv2overlay', label='Draw CV2 Overlay')
		p[0].default = False
		p[0].help = ("Draws boxes/skeletons directly into this TOP's own texture via OpenCV "
			"(draw_tracked_skeletons()), independent of Drawdebug (which only gates whether "
			"DebugBB/DebugKeypoints -- the fast, geometry-instanced debug view driven by "
			"table_output/table_joints/table_bones -- are allowed to cook at all; see "
			"execute_toggle_debug). cv2 drawing is measurably slower and runs on the main "
			"thread inside postprocess(), so leave this off and use Drawdebug's geometry-based "
			"view for normal use -- this is for comparing the two rendering paths directly.")
		scriptOp.par.Drawcv2overlay = False

	def get_model_path(self):
		"""Return path to the MoveNet multipose model."""
		model_dir = os.path.join(project.folder, 'data', 'ml', 'movenet')
		return os.path.join(model_dir, MODEL_FILENAME)

	def on_model_loaded(self, session):
		"""Log model I/O and sanity-check the expected (1, 6, 56) output shape."""
		outputs = session.get_outputs()
		self.printONNX(f"MoveNet model outputs ({len(outputs)}):")
		for i, o in enumerate(outputs):
			self.printONNX(f"  [{i}] name='{o.name}' shape={o.shape} type={o.type}")

		inputs = session.get_inputs()
		for i, inp in enumerate(inputs):
			self.printONNX(f"  input[{i}] name='{inp.name}' shape={inp.shape} type={inp.type}")

		expected_width = NUM_MODEL_KEYPOINTS * 3 + 4 + 1  # keypoints + box + score
		shape = outputs[0].shape if outputs else None
		if not shape or shape[-1] != expected_width:
			self.printONNX(f"WARNING: expected last output dim {expected_width} ({NUM_MODEL_KEYPOINTS}kpts+box+score), got {shape}")

		self.check_providers(session)

		self._cached_input_name = inputs[0].name
		self._cached_output_name = outputs[0].name

	def run_inference(self, input_tensor):
		"""Caches input/output names at load time and passes an explicit single output
		name, instead of the base class default's per-call name lookup and
		output_names=None. Strictly no worse and slightly cheaper per call, but does not
		fully explain this model's slower session.run() vs the legacy script -- see
		Round 9 in td-threaded-inference-optimization.md."""
		return self.session.run([self._cached_output_name], {self._cached_input_name: input_tensor})

	def preprocess(self, nA):
		"""Preprocess input for MoveNet. Model expects an NHWC INT32 tensor with plain
		0-255 pixel values (TF-style) -- NOT the NCHW float32 tensor every other script
		in this project builds. No resizing here: assumes TD has already resized input
		to a multiple-of-32 working resolution upstream (fit_square_sm)."""
		self.original_h, self.original_w = nA.shape[:2]
		num_channels = nA.shape[2] if len(nA.shape) == 3 else 1

		if num_channels >= 3:
			flipped = nA[::-1, :, :3]  # flip V + drop alpha (view, no alloc)
		else:
			flipped = self.npu.grayscale_to_rgb(self.npu.flip_v(nA))

		needed = (1, self.original_h, self.original_w, 3)
		if self._input_buf_shape != needed:
			self._input_tensor_buf = np.empty(needed, dtype=np.int32)
			self._input_buf_shape = needed
		# Denormalize TD's 0-1 float straight into the int32 batch buffer (numpy
		# truncates on assignment, equivalent to the old script's explicit .astype()).
		self._input_tensor_buf[0] = flipped * 255.0

		return self._input_tensor_buf

	def postprocess(self, outputs):
		"""Postprocess MoveNet's (1, 6, 56) output: 6 fixed candidate slots, (y, x,
		score) keypoints and a (ymin, xmin, ymax, xmax) box -- reordered to this
		project's standard (x, y, conf) / xyxy layout immediately below."""
		pred = outputs[0][0]  # (6, 56)

		kpts_raw = pred[:, 0:NUM_MODEL_KEYPOINTS * 3].reshape(-1, NUM_MODEL_KEYPOINTS, 3)  # (6, 17, 3): y, x, score
		boxes_yxyx = pred[:, NUM_MODEL_KEYPOINTS * 3:NUM_MODEL_KEYPOINTS * 3 + 4]  # ymin, xmin, ymax, xmax
		confidences = pred[:, NUM_MODEL_KEYPOINTS * 3 + 4].copy()

		boxes_xyxy = np.stack(
			[boxes_yxyx[:, 1], boxes_yxyx[:, 0], boxes_yxyx[:, 3], boxes_yxyx[:, 2]], axis=1
		).astype(np.float32)
		keypoints = np.stack(
			[kpts_raw[:, :, 1], kpts_raw[:, :, 0], kpts_raw[:, :, 2]], axis=-1
		).astype(np.float32)  # (6, 17, 3): x, y, conf

		# Read thresholds/smoothing from custom parameters (updated each frame)
		self.conf_threshold = self._par_or_default('Confthreshold', CONF_THRESHOLD)
		smoothing = self._par_or_default('Outputsmoothing', OUTPUT_SMOOTHING)
		self.tracker.max_match_dist = self._par_or_default('Maxmatchdist', MAX_MATCH_DIST)
		self.tracker.track_buffer = self._par_or_default('Tracklossframes', TRACKER_MAX_AGE)
		self.tracker.min_hits = int(self._par_or_default('Trackconfirmframes', TRACKER_MIN_HITS))
		min_box_width = self._par_or_default('Minboxwidth', MIN_BOX_WIDTH)
		min_box_height = self._par_or_default('Minboxheight', MIN_BOX_HEIGHT)

		valid = confidences > self.conf_threshold
		valid &= (boxes_xyxy[:, 2] - boxes_xyxy[:, 0] >= min_box_width) & (boxes_xyxy[:, 3] - boxes_xyxy[:, 1] >= min_box_height)
		boxes_xyxy = boxes_xyxy[valid]
		confidences = confidences[valid]
		keypoints = keypoints[valid]

		boxes_xyxy = np.clip(boxes_xyxy, 0.0, 1.0)

		# Flip Y-axis for TouchDesigner (model uses top-down, TD uses bottom-up)
		boxes_xyxy[:, 1], boxes_xyxy[:, 3] = 1.0 - boxes_xyxy[:, 3], 1.0 - boxes_xyxy[:, 1]
		keypoints[:, :, 1] = 1.0 - keypoints[:, :, 1]

		# No box-IoU NMS here -- see module docstring for why it was tried and removed.
		# MoveNet's 6 fixed slots have no built-in de-duplication, but duplicate slots
		# for the same person are handled downstream by KeypointTracker's own
		# keypoint-distance duplicate suppression instead (see its docstring).

		detections = []
		for i in range(len(boxes_xyxy)):
			detections.append({
				'box': boxes_xyxy[i].tolist(),
				'score': float(confidences[i]),
				'keypoints': keypoints[i].tolist(),  # 17 x [x, y, conf]
			})

		active_tracks = self.tracker.update(detections)

		active_ids = {t.track_id for t in active_tracks}
		self.tracked_objects = []
		for t in active_tracks:
			if t.score < self.conf_threshold or not t.confirmed:
				continue
			box_raw = t.box  # last-matched box, held as-is during occlusion -- see
			# object_tracker.KeypointTrack's docstring for why there's no Kalman
			# filter/prediction here. UNSMOOTHED: KeypointTracker (unlike ByteTracker's
			# Kalman filter) applies no damping of its own, so without the same
			# smoothing lerp applied to keypoints below, the box would jump straight to
			# each new detection's raw, keypoint-extent-derived (and therefore noisy --
			# see module docstring) box every matched frame.

			state = self._kpt_state.get(t.track_id)
			raw_kpts = t.payload.get('keypoints')  # 17 x [x, y, conf], model keypoints only
			if state is None:
				smoothed = [list(kp) for kp in raw_kpts] if raw_kpts else [[0.0, 0.0, 0.0]] * NUM_MODEL_KEYPOINTS
				smoothed += [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]  # left_hand, right_hand placeholders
				state = {
					'smoothed': smoothed,
					'lost_frames': [0] * NUM_KEYPOINTS,
					'box': list(box_raw),
				}
				self._kpt_state[t.track_id] = state
			elif t.lost_frames == 0 and raw_kpts is not None:
				for k, (x, y, conf) in enumerate(raw_kpts):
					sx, sy, _ = state['smoothed'][k]
					state['smoothed'][k] = [
						sx * smoothing + x * (1.0 - smoothing),
						sy * smoothing + y * (1.0 - smoothing),
						conf,
					]
					state['lost_frames'][k] = 0
				# Same lerp, same "only advance on a frame that actually matched a real
				# detection" cadence as the keypoints above -- a Kalman-predicted-only
				# frame (lost_frames > 0) has no new box data at all, so just hold the
				# last smoothed value below.
				state['box'] = [
					state['box'][i] * smoothing + box_raw[i] * (1.0 - smoothing)
					for i in range(4)
				]
			if t.lost_frames > 0:
				for k in range(NUM_MODEL_KEYPOINTS):
					state['lost_frames'][k] += 1

			box = state['box']
			cx = (box[0] + box[2]) / 2
			cy = (box[1] + box[3]) / 2
			w = box[2] - box[0]
			h = box[3] - box[1]

			# Computed hand points: a deterministic function of the (already-smoothed)
			# elbow/wrist positions, recomputed fresh every frame rather than smoothed
			# independently -- matches the old script's approach, and inherits the
			# wrist's own visibility/confidence directly.
			for hand_idx, elbow_idx, wrist_idx in ((17, 7, 9), (18, 8, 10)):
				ex, ey, _ = state['smoothed'][elbow_idx]
				wx, wy, wconf = state['smoothed'][wrist_idx]
				state['smoothed'][hand_idx] = [
					wx + (wx - ex) * HAND_EXTENSION,
					wy + (wy - ey) * HAND_EXTENSION,
					wconf,
				]
				state['lost_frames'][hand_idx] = state['lost_frames'][wrist_idx]

			self.tracked_objects.append({
				'track_id': t.track_id,
				'score': t.score,
				'cx': cx, 'cy': cy, 'w': w, 'h': h,
				'x_left': box[0],
				'x_right': box[2],
				'y_top': box[3],
				'y_bottom': box[1],
				'keypoints': state['smoothed'],  # 19 x [x, y, conf], smoothed, TD coords
				'keypoints_visible': [lost <= self.tracker.track_buffer for lost in state['lost_frames']],
				'vx': float(t.mean[4]), 'vy': float(t.mean[5]),
				'lost_frames': t.lost_frames,
				'total_frames': t.total_frames,
			})

		object_tracker.prune_stale(active_ids, self._kpt_state)

		if DRAW_BOXES:
			output_img = self.npu.flip_v(self.draw_tracked_skeletons())
		else:
			needed_shape = (self.original_h, self.original_w, 3)
			if self._output_buf is None or self._output_buf_shape != needed_shape:
				self._output_buf = np.zeros(needed_shape, dtype=np.float32)
				self._output_buf_shape = needed_shape
			output_img = self._output_buf

		return output_img

	def on_result_published(self):
		"""Flush table_output/table_joints/table_bones from tracked_objects right after
		this frame's texture publishes, BEFORE the next frame's capture/dispatch -- see
		the base class's on_result_published() docstring for why this replaces the older
		pending_table_update-flag-checked-by-the-wrapper pattern (see Round 9)."""
		self.write_tracks_to_table()
		self.write_joints_bones_to_tables()

	def draw_tracked_skeletons(self):
		"""Render boxes + skeletons for tracked people onto a blank image.
		Returns an RGB float32 (0-1) image at original resolution."""
		output_img = np.zeros((self.original_h, self.original_w, 3), dtype=np.float32)

		if not self.tracked_objects:
			return output_img

		draw_img = np.zeros((self.original_h, self.original_w, 3), dtype=np.uint8)
		w, h = self.original_w, self.original_h

		def to_px(td_x, td_y):
			return object_tracker.td_to_px(td_x, td_y, w, h)

		for obj in self.tracked_objects:
			if obj['lost_frames'] > 0 and obj['score'] < self.conf_threshold * 0.5:
				continue

			fade = object_tracker.track_fade(obj['lost_frames'], self.tracker.track_buffer)

			box_color = tuple(int(c * fade) for c in PERSON_BOX_COLOR_BGR)
			kpt_color = tuple(int(c * fade) for c in KEYPOINT_COLOR_BGR)
			skel_color = tuple(int(c * fade) for c in SKELETON_COLOR_BGR)

			px1, py_bottom = to_px(obj['x_left'], obj['y_bottom'])
			px2, py_top = to_px(obj['x_right'], obj['y_top'])
			cv2.rectangle(draw_img, (px1, py_top), (px2, py_bottom), box_color, 2)

			label = f"#{obj['track_id']} {obj['score']:.0%}"
			font_scale = 0.5
			(tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
			cv2.rectangle(draw_img, (px1, py_top - th - 6), (px1 + tw + 4, py_top), box_color, -1)
			cv2.putText(draw_img, label, (px1 + 2, py_top - 4),
				cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 0), 1, cv2.LINE_AA)

			kpts = obj['keypoints']  # 19 x [x, y, conf], smoothed
			visible = obj['keypoints_visible']
			pts_px = [to_px(kp[0], kp[1]) if vis else None for kp, vis in zip(kpts, visible)]

			for a, b in SKELETON_EDGES:
				if pts_px[a] is not None and pts_px[b] is not None:
					cv2.line(draw_img, pts_px[a], pts_px[b], skel_color, 2, cv2.LINE_AA)

			for pt in pts_px:
				if pt is not None:
					cv2.circle(draw_img, pt, 3, kpt_color, -1, cv2.LINE_AA)

		return cv2.cvtColor(draw_img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0

	# ==================== CHOP TRACKING OUTPUT ====================
	# See onnx_yolo26_pose.py's identical section -- same tracked_objects shape
	# (19 keypoints here instead of 17), same table_output/table_joints/table_bones
	# convention.

	def write_tracks_to_table(self):
		"""Helper to write current tracking data to a Table DAT."""
		tbl = self.opOutputTableDAT
		if tbl is None:
			return

		kpt_header = []
		for name in KEYPOINT_NAMES:
			kpt_header += [f'{name}_x', f'{name}_y', f'{name}_conf']

		tbl.clear()
		tbl.appendRow([
			*object_tracker.label_header(),
			*object_tracker.box_header(),
			*kpt_header,
			*object_tracker.color_header(),
		])
		for obj in self.tracked_objects:
			flat_kpts = [v for kp in obj['keypoints'] for v in kp]  # 19*3 flat list
			tbl.appendRow([
				*object_tracker.label_row(obj['track_id'], obj['score']),
				*object_tracker.box_row(obj),
				*[f"{v:.4f}" for v in flat_kpts],
				*object_tracker.color_row(obj['track_id']),
			])

	def write_joints_bones_to_tables(self):
		"""Write flattened per-visible-keypoint / per-visible-bone Table DATs -- see
		onnx_yolo26_pose.py's identical method for the full convention."""
		if self.opJointsTableDAT is not None:
			tbl = self.opJointsTableDAT
			tbl.clear()
			tbl.appendRow(object_tracker.joints_header())
			for obj in self.tracked_objects:
				track_id = obj['track_id']
				for name, kp, vis in zip(KEYPOINT_NAMES, obj['keypoints'], obj['keypoints_visible']):
					if vis:
						tbl.appendRow(object_tracker.joints_row(track_id, name, kp[0], kp[1], 0.0, kp[2]))

		if self.opBonesTableDAT is not None:
			tbl = self.opBonesTableDAT
			tbl.clear()
			tbl.appendRow(object_tracker.bones_header())
			for obj in self.tracked_objects:
				track_id = obj['track_id']
				kpts = obj['keypoints']
				vis = obj['keypoints_visible']
				for a, b in SKELETON_EDGES:
					if vis[a] and vis[b]:
						ax, ay, aconf = kpts[a]
						bx2, by2, bconf2 = kpts[b]
						dx = bx2 - ax
						dy = by2 - ay
						mx = (ax + bx2) / 2.0
						my = (ay + by2) / 2.0
						angle = math.degrees(math.atan2(dy, dx))
						length = math.hypot(dx, dy)
						conf = min(aconf, bconf2)
						tbl.appendRow(object_tracker.bones_row(track_id, mx, my, angle, length, conf))


# Create global instance -- shut down any PREVIOUS instance first (releases its
# GPU-resident ONNX Runtime session(s) and stops its worker thread) so a script
# reload during active development doesn't leak both -- see
# onnx_inference_manager.shutdown_and_register()'s docstring for the full
# mechanism this avoids (and why it's NOT TD's own store()/fetch(), which risked
# a real crash trying to persist a live, unpicklable manager instance).
inference_manager = MoveNetPoseInference()
onnx_inference_manager.shutdown_and_register(parent().path, inference_manager)

# TouchDesigner callback wrappers that delegate to the manager
def onSetupParameters(scriptOp):
	return inference_manager.onSetupParameters(scriptOp)


def onPulse(par):
	return inference_manager.onPulse(par)


def onCook(scriptOp):
	# Table writes happen inside this call now, via on_result_published() -- called
	# right after this frame's texture publishes, BEFORE the next frame's capture gets
	# dispatched (see onnx_inference_manager.py's onCook() and MoveNetPoseInference.
	# on_result_published() docstrings). No flag-check needed here anymore.
	inference_manager.onCook(scriptOp)

	# Independent from Drawdebug on purpose -- see Drawcv2overlay's par help. Drawdebug
	# (a COMP-level par) only gates DebugBB/DebugKeypoints cooking (execute_toggle_debug),
	# not this script's own cv2 drawing -- Drawcv2overlay lives on script1 itself, same as
	# every other tracker-specific par set up in onSetupParameters() above.
	global DRAW_BOXES
	DRAW_BOXES = scriptOp.par.Drawcv2overlay.eval() == 1


def onGetCookLevel(scriptOp: scriptCHOP) -> CookLevel:
	"""See onnx_yolo26_seg.py's identical method for why this is unconditionally ALWAYS
	rather than AUTOMATIC."""
	return CookLevel.ALWAYS
