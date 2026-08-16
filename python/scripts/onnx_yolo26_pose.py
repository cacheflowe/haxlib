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
# yolo26n-pose.onnx is an Ultralytics end2end (NMS-free) export.
# Confirmed by inspecting the model's embedded metadata + a dummy inference pass:
#   input:  'pixel_values' (1, 3, 640, 640) float32
#   output: 'logits' (1, 300, 57) float32 -- 300 fixed candidate slots, already
#           sorted/filtered by the graph's own built-in NMS (no NMS needed here).
#   Per-candidate row layout (57 values):
#     [0:4]  box xyxy, normalized 0-1
#     [4]    confidence (already sigmoid-applied, a plain 0-1 probability)
#     [5]    class id (always 0.0 -- this export only has one class: 'person')
#     [6:57] 17 keypoints x (x, y, conf) triples, x/y normalized 0-1, conf a 0-1 probability
# Keypoint order matches the model's own embedded 'kpt_names' metadata (standard COCO-17):
KEYPOINT_NAMES = [
	'nose', 'left_eye', 'right_eye', 'left_ear', 'right_ear',
	'left_shoulder', 'right_shoulder', 'left_elbow', 'right_elbow',
	'left_wrist', 'right_wrist', 'left_hip', 'right_hip',
	'left_knee', 'right_knee', 'left_ankle', 'right_ankle',
]
NUM_KEYPOINTS = len(KEYPOINT_NAMES)  # 17

# COCO-17 skeleton edges (index pairs into KEYPOINT_NAMES), standard Ultralytics layout
SKELETON_EDGES = [
	(0, 1), (0, 2), (1, 3), (2, 4),          # face
	(0, 5), (0, 6), (5, 6),                  # shoulders/neck
	(5, 7), (7, 9), (6, 8), (8, 10),         # arms
	(5, 11), (6, 12), (11, 12),              # torso
	(11, 13), (13, 15), (12, 14), (14, 16),  # legs
]

# Keypoint indices used for KeypointTracker's matching distance -- the STABLE core
# (face, shoulders, hips), excluding elbows/wrists/knees/ankles, which move the most
# frame-to-frame and carry the most jitter. See onnx_movenet.py's identical constant
# for the full rationale (that script's KeypointTracker port is the reference).
_UNSTABLE_KEYPOINT_KEYWORDS = ('elbow', 'wrist', 'knee', 'ankle')
DISTANCE_KEYPOINT_INDICES = [
	i for i, name in enumerate(KEYPOINT_NAMES)
	if not any(kw in name for kw in _UNSTABLE_KEYPOINT_KEYWORDS)
]

# ==================== CONFIGURATION ====================
# Only one pose variant is currently exported: 'yolo26n-pose'
MODEL_VARIANT = 'yolo26s-pose'

# Confidence threshold for a detected person to be shown/tracked (0.0 - 1.0). Tuned live
# for this camera/scene, where real-signal confidence runs extremely low (fractions of a
# percent) -- not a typical detector threshold. KeypointTracker has no ByteTrack-style
# two-stage high/low recovery band, so this is a single admission/display gate.
CONF_THRESHOLD = 0.005

# Tracker: max frames to keep a lost track alive. Tuned live: ~0.25s of grace at 60fps.
TRACKER_MAX_AGE = 15

# Tracker: total matched frames (not necessarily consecutive -- see object_tracker.Track's
# confirmed/hits) a brand-new track needs before it's confirmed and shown/output at all.
# Cuts down on both overlap with existing boxes and single-frame noise "detections"
# registering as a real person -- almost none of that noise ever gets a second real match
# at all before track_buffer prunes it. Costs a few frames of extra latency on every
# genuinely new person's first appearance; once confirmed a track stays confirmed through
# brief occlusion (that's Tracklossframes' job, not this one).
TRACKER_MIN_HITS = 3

# Tracker: max summed keypoint distance (object_tracker.KeypointTracker, restricted to
# DISTANCE_KEYPOINT_INDICES above) to accept a match between a track and a detection --
# NOT a box IoU threshold. This model uses KeypointTracker (keypoint-distance matching)
# rather than box-IoU + Kalman tracking; see Round 9 in td-threaded-inference-optimization.md
# and object_tracker.py's "POSE-SPECIFIC TRACKER" section for why. Starting value carried
# over from onnx_movenet.py's own tuning; re-tune live against this scene.
MAX_MATCH_DIST = 0.5

# Fraction of MAX_MATCH_DIST used as the duplicate-detection suppression threshold --
# see KeypointTracker.update()'s docstring for why this needs to be tighter than the
# match threshold itself.
DUP_DIST_FACTOR = 0.5

# Minimum box width/height (normalized 0-1, fraction of frame dimension) for a detection
# to be kept at all -- applied alongside Confthreshold, before NMS/tracking. A tiny,
# degenerate box is almost never a real person regardless of confidence, so a size floor
# catches noise a confidence threshold alone lets through. Separate width/height floors,
# NOT one shared value: a standing person's box is naturally much narrower than tall
# (~0.4-0.6 width/height is typical), so a single threshold high enough to reject
# small-on-both-axes noise blobs also rejects real, legitimately-tall-but-narrow people.
# Tune independently.
MIN_BOX_WIDTH = 0.02
MIN_BOX_HEIGHT = 0.02

# Smoothing factor for keypoint AND box position lerp -- used for both the debug draw
# and the output table (0 = no smoothing, 1 = frozen). KeypointTracker holds the box at
# its last-matched value with no damping of its own (see object_tracker.KeypointTrack's
# docstring), so this is the ONLY smoothing applied to box position. Tuned for the
# keypoint case originally -- re-verify it still suits box motion too.
OUTPUT_SMOOTHING = 0.23

# Draw skeletons on the output image?
DRAW_BOXES = False

PERSON_BOX_COLOR_BGR = (0, 255, 0)      # Green
SKELETON_COLOR_BGR = (0, 255, 255)      # Yellow
KEYPOINT_COLOR_BGR = (0, 128, 255)      # Orange


# ==================== YOLO26 POSE ESTIMATION ====================

class YOLO26PoseInference(ONNXInferenceManager):
	"""YOLO26 Pose Estimation inference with temporal tracking.

	Targets the Ultralytics end2end (one-to-one trained) ONNX export: single output
	tensor (1, 300, 57), pre-sorted by confidence, already NMS'd by the graph itself, so no
	extra box-IoU NMS pass is applied here -- residual duplicates for the same person are
	handled by KeypointTracker's own keypoint-distance duplicate suppression instead.

	Tracking is split the same way ONNXInferenceManager splits model concerns:
	`object_tracker.KeypointTracker` (shared across every keypoint-based ONNX script in
	this project -- keypoint-distance matching beats box IoU for pose models, see Round 9
	in td-threaded-inference-optimization.md) owns the generic tracking lifecycle: greedy
	keypoint-distance matching, track lifecycle, confidence decay. This class only owns
	what's genuinely pose-specific: per-keypoint smoothing and visibility hysteresis, keyed
	by track_id in self._kpt_state since KeypointTracker itself doesn't smooth anything.
	Keypoint visibility uses the same hold window as track loss (Tracklossframes/
	track_buffer) rather than its own par, since a pose can't outlive the track it belongs to.
	"""

	def __init__(self):
		super().__init__()
		self.opOutputTableDAT = parent().op('table_output')  # Optional Table DAT for structured output
		# Sibling Table DATs at this same parent level, same convention as table_output:
		# written unconditionally every cook, then wired as ordinary COMP inputs into
		# whichever downstream COMP wants them (DebugSkeleton's geo_joints/geo_bones read
		# them via its own In DATs, matching table_output -> input 0 -> in2). This script
		# never reaches into a child COMP by path -- consumers pull data by wiring to this
		# parent, the normal TD dependency-graph way (see write_joints_bones_to_tables()).
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
		self._input_tensor_buf = None   # pre-allocated NCHW input buffer
		self._input_buf_shape = None

	def onSetupParameters(self, scriptOp):
		"""Add YOLO26-Pose-specific parameters alongside base class params."""
		super().onSetupParameters(scriptOp)
		page = scriptOp.appendCustomPage('YOLO26')
		p: Page = page.appendFloat('Confthreshold', label='Confidence Threshold', size=1)
		p[0].default = CONF_THRESHOLD
		p[0].min = 0.0
		p[0].max = 0.05  # real signal in this scene lives near ~0.005 -- 0-1 made the slider unusably coarse
		p[0].clampMin = True
		p[0].clampMax = False  # still typeable above 0.05 for a future scene with normal-range confidences
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
		p[0].max = 90.0  # tuned value is 15 (~0.25s @ 60fps) -- 300 made fine adjustment hard
		p[0].clampMin = True
		p[0].clampMax = False
		p[0].help = object_tracker.par_help('Tracklossframes')
		scriptOp.par.Tracklossframes = TRACKER_MAX_AGE
		p = page.appendFloat('Maxmatchdist', label='Max Match Distance', size=1)
		p[0].default = MAX_MATCH_DIST
		p[0].min = 0.0
		p[0].max = 2.0  # summed across several stable keypoints -- can meaningfully exceed 1.0
		p[0].clampMin = True
		p[0].clampMax = False
		p[0].help = object_tracker.par_help('Maxmatchdist', subject='person')
		scriptOp.par.Maxmatchdist = MAX_MATCH_DIST
		p = page.appendFloat('Trackconfirmframes', label='Track Confirm Frames', size=1)
		p[0].default = TRACKER_MIN_HITS
		p[0].min = 1.0
		p[0].max = 30.0  # tuned default is 3 -- a handful of frames, not tens
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

	def get_model_path(self):
		"""Return path to the YOLO26 pose model."""
		model_dir = os.path.join(project.folder, 'data', 'ml', 'yolo26')
		return os.path.join(model_dir, f'{MODEL_VARIANT}.onnx')

	def on_model_loaded(self, session):
		"""Log model I/O and sanity-check the expected end2end pose output shape."""
		outputs = session.get_outputs()
		self.printONNX(f"YOLO26 Pose model outputs ({len(outputs)}):")
		for i, o in enumerate(outputs):
			self.printONNX(f"  [{i}] name='{o.name}' shape={o.shape} type={o.type}")

		inputs = session.get_inputs()
		for i, inp in enumerate(inputs):
			self.printONNX(f"  input[{i}] name='{inp.name}' shape={inp.shape} type={inp.type}")

		expected_width = 4 + 1 + 1 + NUM_KEYPOINTS * 3  # box + conf + class_id + keypoints
		shape = outputs[0].shape if outputs else None
		if not shape or shape[-1] != expected_width:
			self.printONNX(f"WARNING: expected last output dim {expected_width} (box+conf+cls+{NUM_KEYPOINTS}kpts), got {shape}")

		# Log active execution providers (critical for performance diagnosis)
		self.check_providers(session)

	def preprocess(self, nA):
		"""Preprocess input for the pose model.
		Assumes TD has already resized input to the model's expected dimensions (e.g. 640x640).
		"""
		self.original_h, self.original_w = nA.shape[:2]
		num_channels = nA.shape[2] if len(nA.shape) == 3 else 1

		if num_channels >= 3:
			h, w = self.original_h, self.original_w
			needed = (1, 3, h, w)
			# Allocate buffer only when dimensions change
			if self._input_buf_shape != needed:
				self._input_tensor_buf = np.empty(needed, dtype=np.float32)
				self._input_buf_shape = needed
			# Flip vertically + RGB + CHW copy into pre-allocated buffer
			flipped = nA[::-1, :, :3]  # view, no alloc
			self._input_tensor_buf[0, 0] = flipped[:, :, 0]
			self._input_tensor_buf[0, 1] = flipped[:, :, 1]
			self._input_tensor_buf[0, 2] = flipped[:, :, 2]
		else:
			nA = self.npu.flip_v(nA)
			nA = self.npu.grayscale_to_rgb(nA)
			self._input_tensor_buf = np.ascontiguousarray(nA.transpose(2, 0, 1)[np.newaxis], dtype=np.float32)
			self._input_buf_shape = self._input_tensor_buf.shape

		return self._input_tensor_buf

	def postprocess(self, outputs):
		"""Postprocess YOLO26 pose outputs: end2end format, already NMS'd by the graph.

		pred columns: [0:4]=box xyxy (0-1), [4]=conf, [5]=class_id (always 0),
		[6:57]=17 keypoints x (x, y, conf), all normalized 0-1.
		"""
		pred = outputs[0][0]  # (300, 57)

		boxes_xyxy = pred[:, 0:4].copy()
		confidences = pred[:, 4].copy()
		keypoints = pred[:, 6:6 + NUM_KEYPOINTS * 3].reshape(-1, NUM_KEYPOINTS, 3).copy()

		# Read thresholds/smoothing from custom parameters (updated each frame)
		self.conf_threshold = self._par_or_default('Confthreshold', CONF_THRESHOLD)
		smoothing = self._par_or_default('Outputsmoothing', OUTPUT_SMOOTHING)
		self.tracker.max_match_dist = self._par_or_default('Maxmatchdist', MAX_MATCH_DIST)
		self.tracker.track_buffer = self._par_or_default('Tracklossframes', TRACKER_MAX_AGE)
		self.tracker.min_hits = int(self._par_or_default('Trackconfirmframes', TRACKER_MIN_HITS))
		min_box_width = self._par_or_default('Minboxwidth', MIN_BOX_WIDTH)
		min_box_height = self._par_or_default('Minboxheight', MIN_BOX_HEIGHT)

		valid = confidences > self.conf_threshold
		# Reject degenerate tiny boxes regardless of confidence -- see MIN_BOX_WIDTH/HEIGHT
		# comment for why these are separate thresholds, not one shared value.
		valid &= (boxes_xyxy[:, 2] - boxes_xyxy[:, 0] >= min_box_width) & (boxes_xyxy[:, 3] - boxes_xyxy[:, 1] >= min_box_height)
		boxes_xyxy = boxes_xyxy[valid]
		confidences = confidences[valid]
		keypoints = keypoints[valid]

		# Clip boxes to [0, 1]
		boxes_xyxy = np.clip(boxes_xyxy, 0.0, 1.0)

		# Flip Y-axis for TouchDesigner (model uses top-down, TD uses bottom-up)
		boxes_xyxy[:, 1], boxes_xyxy[:, 3] = 1.0 - boxes_xyxy[:, 3], 1.0 - boxes_xyxy[:, 1]
		keypoints[:, :, 1] = 1.0 - keypoints[:, :, 1]

		# No box-IoU NMS here -- see class docstring: this model's end2end export already
		# NMS's itself, and residual duplicates are handled by KeypointTracker instead.

		# Build detection list for the tracker. No detection-count cap here: KeypointTracker's
		# max_tracks bounds worst-case track-count growth, and its greedy distance-sort
		# matching is far cheaper than ByteTracker's Hungarian assignment was at this scale.
		detections = []
		for i in range(len(boxes_xyxy)):
			detections.append({
				'box': boxes_xyxy[i].tolist(),
				'score': float(confidences[i]),
				'keypoints': keypoints[i].tolist(),  # 17 x [x, y, conf]
			})

		# Update tracker (runs on main thread, no lock needed)
		active_tracks = self.tracker.update(detections)

		# Build structured data for CHOP/table output (filter out decayed tracks).
		# active_ids covers every track the tracker is still maintaining, not just the
		# ones cleared for display below -- a track kept alive via low-confidence recovery
		# (score hovering just under Confthreshold) must keep its keypoint-smoothing state,
		# so scoping this to the display-filtered subset would wipe and restart smoothing
		# every frame for any such track.
		active_ids = {t.track_id for t in active_tracks}
		self.tracked_objects = []
		for t in active_tracks:
			# t.confirmed gates display same as the score check: a track still in its
			# min_hits confirmation window is kept in active_ids but not yet shown.
			if t.score < self.conf_threshold or not t.confirmed:
				continue
			# Last-matched box, held as-is during occlusion (no Kalman filter/prediction --
			# see object_tracker.KeypointTrack's docstring). KeypointTracker applies no
			# damping of its own, so the smoothing lerp below is what keeps this from
			# jumping straight to each new detection's raw box every matched frame.
			box_raw = t.box

			state = self._kpt_state.get(t.track_id)
			raw_kpts = t.payload.get('keypoints')
			if state is None:
				# Brand-new track: seed smoothed state directly from its first detection.
				state = {
					'smoothed': [list(kp) for kp in raw_kpts] if raw_kpts else [[0.0, 0.0, 0.0]] * NUM_KEYPOINTS,
					'lost_frames': [0] * NUM_KEYPOINTS,
					'box': list(box_raw),
				}
				self._kpt_state[t.track_id] = state
			elif t.lost_frames == 0 and raw_kpts is not None:
				# Only advance keypoint smoothing on a frame where this track actually
				# matched a real detection -- a frame with no fresh match (lost_frames > 0)
				# has no new keypoint data at all, so just let the hold counters age below.
				# No per-keypoint confidence gate: this model's per-keypoint confidence
				# values run far too low to be a meaningful signal on their own, so if the
				# box cleared Confthreshold, its keypoints are used as-is.
				for k, (x, y, conf) in enumerate(raw_kpts):
					sx, sy, _ = state['smoothed'][k]
					state['smoothed'][k] = [
						sx * smoothing + x * (1.0 - smoothing),
						sy * smoothing + y * (1.0 - smoothing),
						conf,
					]
					state['lost_frames'][k] = 0
				# Same lerp, same "only advance on a frame that actually matched a real
				# detection" cadence as the keypoints above.
				state['box'] = [
					state['box'][i] * smoothing + box_raw[i] * (1.0 - smoothing)
					for i in range(4)
				]
			if t.lost_frames > 0:
				for k in range(NUM_KEYPOINTS):
					state['lost_frames'][k] += 1

			box = state['box']
			cx = (box[0] + box[2]) / 2
			cy = (box[1] + box[3]) / 2
			w = box[2] - box[0]
			h = box[3] - box[1]

			self.tracked_objects.append({
				'track_id': t.track_id,
				'score': t.score,
				'cx': cx, 'cy': cy, 'w': w, 'h': h,
				'x_left': box[0],
				'x_right': box[2],
				'y_top': box[3],     # top edge of bbox (TD coords)
				'y_bottom': box[1],  # bottom edge of bbox (TD coords)
				'keypoints': state['smoothed'],  # 17 x [x, y, conf], smoothed, TD coords
				'keypoints_visible': [lost <= self.tracker.track_buffer for lost in state['lost_frames']],
				'vx': float(t.mean[4]), 'vy': float(t.mean[5]),  # frame-to-frame box-center delta (see KeypointTrack.mean)
				'lost_frames': t.lost_frames,
				'total_frames': t.total_frames,
			})

		# Prune keypoint smoothing state for tracks the tracker has dropped entirely.
		object_tracker.prune_stale(active_ids, self._kpt_state)

		# Draw output image
		if DRAW_BOXES:
			output_img = self.npu.flip_v(self.draw_tracked_skeletons())
		else:
			# Black frame — no need to zero or flip each frame, just reuse static buffer
			needed_shape = (self.original_h, self.original_w, 3)
			if self._output_buf is None or self._output_buf_shape != needed_shape:
				self._output_buf = np.zeros(needed_shape, dtype=np.float32)
				self._output_buf_shape = needed_shape
			output_img = self._output_buf

		return output_img

	def on_result_published(self):
		"""Flush table_output/table_joints/table_bones from tracked_objects right after
		this frame's texture publishes, before the next frame's capture/dispatch -- see
		ONNXInferenceManager.on_result_published()'s docstring."""
		self.write_tracks_to_table()
		self.write_joints_bones_to_tables()

	def draw_tracked_skeletons(self):
		"""Render boxes + skeletons for tracked people onto a blank image.
		Returns an RGB float32 (0-1) image at original resolution."""
		output_img = np.zeros((self.original_h, self.original_w, 3), dtype=np.float32)

		if not self.tracked_objects:
			return output_img

		# Work in uint8 for cv2 drawing, then convert back
		draw_img = np.zeros((self.original_h, self.original_w, 3), dtype=np.uint8)
		w, h = self.original_w, self.original_h

		def to_px(td_x, td_y):
			"""TD-normalized coords (y: 0=bottom, 1=top) -> pixel (col, row) in this
			function's plain top-down array (row 0 = top). The caller flips the whole
			image back to TD's bottom-up convention afterward (see postprocess())."""
			return object_tracker.td_to_px(td_x, td_y, w, h)

		for obj in self.tracked_objects:
			if obj['lost_frames'] > 0 and obj['score'] < self.conf_threshold * 0.5:
				continue  # Skip faded-out unmatched tracks

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

			kpts = obj['keypoints']  # 17 x [x, y, conf], smoothed
			visible = obj['keypoints_visible']  # 17 x bool, hysteresis-gated by Tracklossframes
			pts_px = [to_px(kp[0], kp[1]) if vis else None for kp, vis in zip(kpts, visible)]

			for a, b in SKELETON_EDGES:
				if pts_px[a] is not None and pts_px[b] is not None:
					cv2.line(draw_img, pts_px[a], pts_px[b], skel_color, 2, cv2.LINE_AA)

			for pt in pts_px:
				if pt is not None:
					cv2.circle(draw_img, pt, 3, kpt_color, -1, cv2.LINE_AA)

		# Convert BGR uint8 -> RGB float32 (0-1)
		return cv2.cvtColor(draw_img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0

	# ==================== CHOP TRACKING OUTPUT ====================
	# To output tracking data to a CHOP, use a Script CHOP DAT with:
	#
	#   mgr = op('script1').module.inference_manager
	#   tracks = mgr.tracked_objects  # list of dicts
	#
	# Each dict contains: track_id, score, cx, cy, w, h, x_left, x_right,
	#   y_top, y_bottom, keypoints (17 x [x, y, conf], smoothed), keypoints_visible
	#   (17 x bool, hysteresis-gated), vx, vy (frame-to-frame box-center delta), lost_frames, total_frames
	#
	# For a Table DAT approach, call write_tracks_to_table() from a
	# Script DAT or Execute DAT each frame.

	def write_tracks_to_table(self):
		"""Helper to write current tracking data to a Table DAT.
		Call from an Execute DAT's onFrameStart or a Timer callback.
		tracked_objects already holds smoothed values (see postprocess()),
		so this just formats them -- no smoothing happens here."""
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
			flat_kpts = [v for kp in obj['keypoints'] for v in kp]  # 17*3 flat list
			tbl.appendRow([
				*object_tracker.label_row(obj['track_id'], obj['score']),
				*object_tracker.box_row(obj),
				*[f"{v:.4f}" for v in flat_kpts],
				*object_tracker.color_row(obj['track_id']),
			])

	def write_joints_bones_to_tables(self):
		"""Write flattened per-visible-keypoint / per-visible-bone Table DATs, one row
		per visible keypoint or bone across ALL tracked people (no fixed per-person/
		per-joint slot layout, so there's no cap on how many people/joints get instanced
		at once). Written unconditionally every cook, same as write_tracks_to_table() --
		these are parent-level data outputs, not debug-view-gated; whether anything
		downstream (e.g. DebugSkeleton's geo_joints/geo_bones instancing) is actually
		looking at them is up to how they're wired, not this method."""
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
# reload during active development doesn't leak both. See Round 7/8 in
# td-threaded-inference-optimization.md and onnx_inference_manager.shutdown_and_register().
inference_manager = YOLO26PoseInference()
onnx_inference_manager.shutdown_and_register(parent().path, inference_manager)

# TouchDesigner callback wrappers that delegate to the manager
def onSetupParameters(scriptOp):
	return inference_manager.onSetupParameters(scriptOp)


def onPulse(par):
	return inference_manager.onPulse(par)


def onCook(scriptOp):
	# Run base manager cook (handles model loading, inference dispatch, copyNumpyArray)
	inference_manager.onCook(scriptOp)

	# Optionally draw skeletons on main thread to avoid threading issues with OpenCV (if enabled)
	global DRAW_BOXES
	DRAW_BOXES = parent().par.Drawdebug.eval() == 1


def onGetCookLevel(scriptOp: scriptCHOP) -> CookLevel:
	"""
	Sets the scriptOp's cook level, the conditions necessary to cause a cook.

	Return one of the following:
		CookLevel.AUTOMATIC - inputs changed and output being used. TD default behavior.
		CookLevel.ON_CHANGE - inputs changed, output used or not.
		CookLevel.WHEN_USED - every frame when output is being used
		CookLevel.ALWAYS - every frame

	AUTOMATIC alone can't drive this pipeline: DebugSkeleton's script_joints/script_bones
	read tracked_objects directly via a raw Python module reference
	(op('../script1_callbacks').module.inference_manager), not through any wire or
	parameter TD's dependency graph can see -- so AUTOMATIC's "is the output being used"
	check stops cooking the moment nothing is directly viewing this TOP's own pixels,
	even though downstream visualization still depends on it.

	Unconditionally ALWAYS rather than switching to AUTOMATIC while paused: once AUTOMATIC
	settles into "not cooking," resuming play isn't a registered dependency of this op, so
	it never recovers on its own. The play/pause skip instead lives in
	ONNXInferenceManager.onCook() itself (checks scriptOp.time.play and returns early),
	which keeps this op always eligible to cook so the next real cook after resuming
	naturally picks back up.
	"""

	return CookLevel.ALWAYS
