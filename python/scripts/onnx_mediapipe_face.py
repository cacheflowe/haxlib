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
_track_color = object_tracker.track_color

# ==================== CONFIGURATION ====================
# MediaPipe BlazeFace (face detector) + FaceMesh (468-point face landmark model),
# Qualcomm AI Hub ONNX exports (data/ml/mediapipe/). Two-stage, like onnx_hsemotion.py:
# face DETECTION runs through the normal threaded ONNXInferenceManager pipeline; per-face
# LANDMARK inference runs synchronously on the main thread inside postprocess(), batched
# across every currently-tracked face into one call (same MAX_BATCH_FACES fixed-size-
# padding trick as onnx_hsemotion.py -- see Round 5 in
# .ai/skills/td-threaded-inference-optimization.md for why a varying batch size is a
# severe ORT performance trap, not just a correctness nicety).
DETECTOR_MODEL_FILENAME = 'face_detector.onnx'
LANDMARK_MODEL_FILENAME = 'face_landmark_detector.onnx'

# ---- BlazeFace anchor generation ----
# Params match MediaPipe's own SsdAnchorsCalculatorOptions/FaceDetectionOptions
# (mediapipe/modules/face_detection/{face_detection,face_detection_short_range}.pbtxt):
# fixed_anchor_size=true (anchor w/h always 1.0 -- box decode relies entirely on the
# x/y/w/h_scale below, not the anchor's own size), num_layers=4, strides=[8,16,16,16] @
# 128x128 input, num_boxes=896. This export uses 256x256 (2x); the anchor grid topology is
# resolution-independent (normalized 0-1 coordinates), so strides/scale just scale
# proportionally with input size. Regenerated automatically if Inputwidth ever changes
# (see preprocess()'s shape-change handling). GenerateAnchors() itself
# (mediapipe/calculators/tflite/ssd_anchors_calculator.cc) merges CONSECUTIVE layers
# sharing the same stride into one group before computing feature-map size.
NUM_LAYERS = 4
BASE_STRIDES = [8, 16, 16, 16]     # at the model's native 128x128; scaled by preprocess()
MIN_SCALE = 0.1484375
MAX_SCALE = 0.75
ANCHOR_OFFSET = 0.5
ASPECT_RATIOS = [1.0]
INTERPOLATED_SCALE_ASPECT_RATIO = 1.0
NUM_KEYPOINTS = 6  # right_eye, left_eye, nose_tip, mouth, right_ear, left_ear

# ---- Rotation-aligned ROI (for the landmark model) ----
# Per mediapipe/modules/face_landmark/face_detection_front_detection_to_roi.pbtxt: rotation
# is computed from keypoint 0 -> keypoint 1 (the two eyes) so the eye line becomes
# horizontal (target_angle=0), then RectTransformationCalculator expands the box by
# ROI_SCALE in both dimensions and forces it square (using the longer side). MediaPipe's
# own default (1.5) crops the chin slightly; 2.0 gives comfortable margin with no
# correctness difference, just framing -- used here.
ROI_SCALE = 2.0
LANDMARK_INPUT_SIZE = 192
NUM_LANDMARKS = 468

# Fixed ceiling for the per-face landmark batch (see MAX_BATCH_FACES in onnx_hsemotion.py
# for the full ORT shape-cache reasoning this avoids).
MAX_BATCH_FACES = 8

CONF_THRESHOLD = 0.5
LOW_CONF_THRESHOLD = 0.3
NMS_IOU_THRESHOLD = 0.3  # matches NonMaxSuppressionCalculator's min_suppression_threshold
MIN_BOX_WIDTH = 0.02
MIN_BOX_HEIGHT = 0.02
TRACKER_MAX_AGE = 30
TRACKER_IOU_THRESHOLD = 0.3
TRACKER_MIN_HITS = 3
OUTPUT_SMOOTHING = 0.5
DRAW_BOXES = False


def _sigmoid(x):
	return 1.0 / (1.0 + np.exp(-np.clip(x, -60, 60)))


def _calculate_scale(min_scale, max_scale, stride_index, num_strides):
	if num_strides == 1:
		return (min_scale + max_scale) * 0.5
	return min_scale + (max_scale - min_scale) * stride_index / (num_strides - 1)


def _generate_anchors(input_size, strides):
	"""Faithful port of ssd_anchors_calculator.cc's GenerateAnchors() -- see BASE_STRIDES
	comment block for what's been verified against the real source, including the
	same-stride-layer merging behavior a naive per-layer implementation would miss."""
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
					# fixed_anchor_size=true -> anchor w/h always 1.0 (see class docstring)
					anchors.append([(x + ANCHOR_OFFSET) / fm, (y + ANCHOR_OFFSET) / fm, 1.0, 1.0])
		layer_id = last_same_stride_layer
	return np.array(anchors, dtype=np.float32)


# ==================== HEAD POSE (yaw/pitch/roll) ====================
# Same data-output scheme as onnx_yunet.py's own head-pose implementation (Posemethod/
# Poseyawscale/Posepitchscale/Posefocalscale/Posesmoothing pars, yaw/pitch/roll columns
# appended to table_output in degrees) -- ported here because FaceMesh's 468 landmarks
# give a much richer, better-distributed correspondence set than YuNet's 5 sparse
# keypoints. YuNet's solvePnP over just 5 near-planar points is an ill-conditioned solve,
# jittery enough that geometric ratios won out as the default there; FaceMesh's 6 pose
# points span the FULL face (forehead-to-chin via the chin point, ear-to-ear via the
# eye/mouth corners), which conditions solvePnP much better -- so POSE_METHOD defaults
# to 'solvepnp' here, unlike YuNet's default.
#
# Landmark indices below are MediaPipe FaceMesh's own well-known canonical layout
# (the same 6-point nose/chin/eye-corners/mouth-corners set used across most
# MediaPipe-based head-pose tutorials/repos) -- FaceMesh's own point ORDER is model-
# defined and consistent frame to frame, so these indices are stable regardless of which
# face is tracked.
POSE_NOSE_TIP = 1
POSE_CHIN = 152
POSE_EYE_R = 33     # outer corner, one side (see _HEAD_MODEL_POINTS -- L/R naming is
POSE_EYE_L = 263    # this script's own consistent convention, not verified against
POSE_MOUTH_R = 61   # true anatomical left/right; getting it backwards only flips
POSE_MOUTH_L = 291  # yaw's sign globally, easily corrected live if needed)
POSE_LANDMARK_INDICES = [POSE_NOSE_TIP, POSE_CHIN, POSE_EYE_R, POSE_EYE_L, POSE_MOUTH_R, POSE_MOUTH_L]

POSE_METHOD = 'solvepnp'  # or 'geometric' -- see module comment for why solvepnp is
# the default here (unlike onnx_yunet.py), given FaceMesh's much richer point set.
POSE_YAW_SCALE = 340.0
POSE_PITCH_SCALE = 100.0
POSE_FOCAL_SCALE = 1.0
POSE_SMOOTHING = 0.5

# Rough canonical 3D face model (average adult proportions, not subject-specific --
# solvePnP only needs plausible relative proportions to recover orientation, not exact
# measurements), matched 1:1 against POSE_LANDMARK_INDICES above. Y-DOWN convention
# (X=right, Y=down, Z=away from camera) -- same as onnx_yunet.py's own model: with Y-up,
# the solver's identity-rotation initial guess would map model-space onto camera-space
# upside-down, pulling the solve toward a spurious ~180-degree-pitch local optimum.
# Adapted from the classic 6-point head-pose model (nose tip, chin, eye corners, mouth
# corners) used widely in OpenCV solvePnP head-pose tutorials.
_HEAD_MODEL_POINTS = np.array([
	(   0.0,    0.0,    0.0),  # nose tip (most forward point -- the origin)
	(   0.0,  330.0,  -65.0),  # chin
	(-225.0, -170.0, -135.0),  # eye_r outer corner
	( 225.0, -170.0, -135.0),  # eye_l outer corner
	(-150.0,  150.0, -125.0),  # mouth_r corner
	( 150.0,  150.0, -125.0),  # mouth_l corner
], dtype=np.float64)


def _rotation_matrix_to_euler(R):
	"""Rotation matrix -> (pitch, yaw, roll) in radians, extrinsic X-Y-Z (Tait-Bryan)
	decomposition -- the standard convention used across OpenCV head-pose tutorials.
	Identical to onnx_yunet.py's own helper."""
	sy = math.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2)
	if sy >= 1e-6:
		pitch = math.atan2(R[2, 1], R[2, 2])
		yaw = math.atan2(-R[2, 0], sy)
		roll = math.atan2(R[1, 0], R[0, 0])
	else:
		pitch = math.atan2(-R[1, 2], R[1, 1])
		yaw = math.atan2(-R[2, 0], sy)
		roll = 0.0
	return pitch, yaw, roll


def _compute_head_direction_geometric(pose_pts, yaw_scale=340.0, pitch_scale=100.0):
	"""Estimate head yaw/pitch/roll from keypoint GEOMETRY directly, no 3D model or
	solver involved -- same bounded-distance-ratio heuristic as onnx_yunet.py's
	identical function, just fed FaceMesh's 6 pose landmarks (native/pre-TD-flip pixel
	coords) instead of YuNet's 5. Kept for output-scheme parity / as a fallback;
	solvepnp (POSE_METHOD's default here) is the more stable option given FaceMesh's
	wider point spread.

	pose_pts: dict with keys 'nose', 'chin', 'eye_r', 'eye_l', 'mouth_r', 'mouth_l',
	each a (x, y) pixel-space pair (native/pre-TD-flip orientation)."""
	nose = np.array(pose_pts['nose'])
	eye_r = np.array(pose_pts['eye_r'])
	eye_l = np.array(pose_pts['eye_l'])
	mouth_r = np.array(pose_pts['mouth_r'])
	mouth_l = np.array(pose_pts['mouth_l'])

	dist_r = np.linalg.norm(nose - eye_r) + np.linalg.norm(nose - mouth_r)
	dist_l = np.linalg.norm(nose - eye_l) + np.linalg.norm(nose - mouth_l)
	yaw_ratio = (dist_r - dist_l) / max(dist_l + dist_r, 1e-6)

	eye_mid = (eye_r + eye_l) * 0.5
	mouth_mid = (mouth_r + mouth_l) * 0.5
	dist_eyes = np.linalg.norm(nose - eye_mid)
	dist_mouth = np.linalg.norm(nose - mouth_mid)
	pitch_ratio = (dist_eyes - dist_mouth) / max(dist_mouth + dist_eyes, 1e-6)

	dx = eye_l[0] - eye_r[0]
	dy = eye_l[1] - eye_r[1]
	roll = math.degrees(math.atan2(dy, dx))

	yaw_ratio = max(-1.0, min(1.0, yaw_ratio))
	pitch_ratio = max(-1.0, min(1.0, pitch_ratio))
	return yaw_ratio * yaw_scale, pitch_ratio * pitch_scale, roll


def _compute_head_direction_solvepnp(pose_pts, width, height, focal_scale=1.0):
	"""Estimate real 3D head rotation -- yaw, pitch, roll, all in DEGREES -- via
	cv2.solvePnP, matching FaceMesh's 6 pose landmarks against _HEAD_MODEL_POINTS.
	Identical approach/API to onnx_yunet.py's own solvepnp function -- see that
	docstring for the full reasoning (focal_scale, the ITERATIVE+explicit-guess choice
	to avoid the near-planar flip ambiguity, yaw/pitch/roll axis meaning). The one
	difference: this uses 6 points spread across the WHOLE face rather than 5 points
	clustered in the eye/nose/mouth region, which conditions the solve better.

	pose_pts: same dict shape as _compute_head_direction_geometric, but in TRUE-FRAME
	pixel coordinates (width x height), NOT the square working buffer -- consistent
	with this script's other true-pixel-space fixes (see docs/learnings/
	debug-comp-camera-aspect.md) so this doesn't reintroduce an aspect-distortion bug
	into the pose solve.

	Returns (0.0, 0.0, 0.0) if the solve fails.
	"""
	image_points = np.array([
		pose_pts['nose'], pose_pts['chin'], pose_pts['eye_r'], pose_pts['eye_l'],
		pose_pts['mouth_r'], pose_pts['mouth_l'],
	], dtype=np.float64)

	focal_length = width * focal_scale
	center = (width / 2.0, height / 2.0)
	camera_matrix = np.array([
		[focal_length, 0.0, center[0]],
		[0.0, focal_length, center[1]],
		[0.0, 0.0, 1.0],
	], dtype=np.float64)
	dist_coeffs = np.zeros((4, 1))

	rvec_guess = np.zeros((3, 1), dtype=np.float64)
	tvec_guess = np.array([[0.0], [0.0], [focal_length]], dtype=np.float64)
	success, rotation_vector, _ = cv2.solvePnP(
		_HEAD_MODEL_POINTS, image_points, camera_matrix, dist_coeffs,
		rvec_guess, tvec_guess, useExtrinsicGuess=True,
		flags=cv2.SOLVEPNP_ITERATIVE,
	)
	if not success:
		return 0.0, 0.0, 0.0

	rotation_matrix, _ = cv2.Rodrigues(rotation_vector)
	pitch, yaw, roll = _rotation_matrix_to_euler(rotation_matrix)
	# pitch and roll both need negating to match expected sign (nodding down should read
	# negative, not positive; same for tilt) -- yaw does not.
	return math.degrees(yaw), -math.degrees(pitch), -math.degrees(roll)


# ==================== MEDIAPIPE FACE + LANDMARK TRACKING ====================

class MediaPipeFaceInference(ONNXInferenceManager):
	"""MediaPipe BlazeFace detector + FaceMesh landmark model, adapted to this project's
	shared ONNXInferenceManager + ByteTracker pattern -- see onnx_hsemotion.py for the
	two-stage (threaded detector + synchronous batched secondary model) architecture this
	mirrors, and MAX_BATCH_FACES's comment for why the secondary batch is padded to a
	fixed size.

	The landmark stage here is more involved than HSEmotion's straight axis-aligned crop:
	MediaPipe's own accuracy depends on a ROTATION-ALIGNED crop (using the two eye
	keypoints to un-rotate the face before landmarking) -- see ROI_SCALE's comment block.
	Each tracked face gets its own affine transform; postprocess() extracts each face's
	own 192x192 aligned crop via cv2.warpAffine, batches them into one landmark-model
	call, then maps each face's 468 output landmarks back through the INVERSE of that
	same affine into original-frame normalized coordinates -- landmarks stored on
	tracked_objects are always in that original-frame space, never the per-face
	aligned-crop space.
	"""

	def __init__(self):
		super().__init__()
		self.opOutputTableDAT = parent().op('table_output')
		self.opJointsTableDAT = parent().op('table_joints')
		self.conf_threshold = CONF_THRESHOLD
		self.low_conf_threshold = LOW_CONF_THRESHOLD
		self.tracker = ByteTracker(
			high_thresh=CONF_THRESHOLD, low_thresh=LOW_CONF_THRESHOLD,
			match_thresh=TRACKER_IOU_THRESHOLD, track_buffer=TRACKER_MAX_AGE,
			min_hits=TRACKER_MIN_HITS,
		)
		self._box_state = {}
		# Per-track smoothed landmarks (shape (468,3), original-frame normalized coords),
		# keyed by track_id -- held/blended across frames the same way box position is.
		self._landmark_state = {}
		# Per-track head-pose state (yaw/pitch/roll in degrees), keyed by track_id --
		# same role as onnx_yunet.py's _kpt_state, separate smoothing pass on top of the
		# already-smoothed landmarks (see Posesmoothing par help).
		self._pose_state = {}
		self.tracked_objects = []
		self._input_tensor_buf = None
		self._input_buf_shape = None
		self._output_buf = None
		self._output_buf_shape = None
		self.original_h = None
		self.original_w = None
		# True (pre-square) source dimensions -- see preprocess()'s fetch and
		# _run_landmarks_batch's docstring for why these matter for the rotation step.
		self._true_w = None
		self._true_h = None
		# Anchors regenerated whenever input resolution changes (see preprocess()) --
		# None until the first real frame, matching _input_buf_shape's own lazy pattern.
		self._anchors = None
		self._anchor_input_size = None
		# Kept from preprocess() (main thread) for postprocess()'s face-crop step -- the
		# SAME resized RGB frame the detector runs on, a plain owned numpy copy (not a
		# view into TD's own buffer, which isn't safe to hold past the frame it was
		# captured in).
		self._last_frame_rgb = None
		# Second, unthreaded ONNX session for landmark inference -- loaded once alongside
		# the detector in on_model_loaded(). Called synchronously from postprocess()
		# (main thread), never from the worker thread.
		self._landmark_session = None

	def onSetupParameters(self, scriptOp):
		"""Add MediaPipe-Face-specific parameters alongside base class params."""
		super().onSetupParameters(scriptOp)
		page = scriptOp.appendCustomPage('MediaPipeFace')
		p = page.appendFloat('Confthreshold', label='Confidence Threshold', size=1)
		p[0].default = CONF_THRESHOLD
		p[0].min = 0.0
		p[0].max = 1.0
		p[0].clampMin = True
		p[0].clampMax = True
		p[0].help = object_tracker.par_help('Confthreshold', subject='face', subject_plural='faces')
		scriptOp.par.Confthreshold = CONF_THRESHOLD
		p = page.appendFloat('Lowconfthreshold', label='Low Confidence Threshold (Recovery)', size=1)
		p[0].default = LOW_CONF_THRESHOLD
		p[0].min = 0.0
		p[0].max = 1.0
		p[0].clampMin = True
		p[0].clampMax = True
		p[0].help = object_tracker.par_help('Lowconfthreshold', subject='face', subject_plural='faces')
		scriptOp.par.Lowconfthreshold = LOW_CONF_THRESHOLD
		p = page.appendFloat('Nmsiouthreshold', label='NMS IoU Threshold (Dedup)', size=1)
		p[0].default = NMS_IOU_THRESHOLD
		p[0].min = 0.0
		p[0].max = 1.0
		p[0].clampMin = True
		p[0].clampMax = True
		p[0].help = object_tracker.par_help('Nmsiouthreshold', subject='face', subject_plural='faces')
		scriptOp.par.Nmsiouthreshold = NMS_IOU_THRESHOLD
		p = page.appendFloat('Minboxwidth', label='Min Box Width', size=1)
		p[0].default = MIN_BOX_WIDTH
		p[0].min = 0.0
		p[0].max = 0.2
		p[0].clampMin = True
		p[0].clampMax = False
		p[0].help = object_tracker.par_help('Minboxwidth', shape_note=(
			"faces are naturally close to square, but this still guards against degenerate "
			"slivers the same way every other detector in this project does."
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
		p = page.appendFloat('Roiscale', label='Landmark ROI Scale', size=1)
		p[0].default = ROI_SCALE
		p[0].min = 1.0
		p[0].max = 4.0
		p[0].clampMin = True
		p[0].clampMax = False
		p[0].help = ("How much to expand the detected face box (both dimensions, then forced "
			"square) before extracting the rotation-aligned crop fed to the landmark model. "
			"MediaPipe's own default is 1.5, which crops the chin slightly on some faces -- 2.0 "
			"(this script's default) gives more margin with no accuracy cost, just framing.")
		scriptOp.par.Roiscale = ROI_SCALE
		p = page.appendMenu('Posemethod', label='Head Pose Method', size=1)
		p[0].menuNames = ['geometric', 'solvepnp']
		p[0].menuLabels = ['Geometric (Keypoint Ratios)', 'SolvePnP (3D Model)']
		p[0].default = POSE_METHOD
		p[0].help = ("Which method estimates yaw/pitch/roll from the 6 pose landmarks "
			"(nose/chin/eye corners/mouth corners). Geometric: bounded distance ratios, unitless "
			"degrees via Poseyawscale/Posepitchscale, very stable but not a calibrated real angle. "
			"SolvePnP: matches against a canonical 3D face model for a genuine 3D rotation in "
			"degrees (see Posefocalscale) -- defaults to this here (unlike onnx_yunet.py, which "
			"defaults to geometric) since FaceMesh's 6 points span the whole face rather than "
			"clustering in the eye/nose/mouth region, conditioning the solve much better.")
		scriptOp.par.Posemethod = POSE_METHOD
		p = page.appendFloat('Poseyawscale', label='Head Pose Yaw Scale (Geometric)', size=1)
		p[0].default = POSE_YAW_SCALE
		p[0].help = ("Degrees-per-ratio scale for yaw specifically (only used when Head Pose "
			"Method = Geometric) -- kept separate from Pitch Scale since yaw's underlying ratio "
			"covers a much smaller natural range than pitch's for the same real rotation.")
		scriptOp.par.Poseyawscale = POSE_YAW_SCALE
		p = page.appendFloat('Posepitchscale', label='Head Pose Pitch Scale (Geometric)', size=1)
		p[0].default = POSE_PITCH_SCALE
		p[0].help = ("Degrees-per-ratio scale for pitch specifically (only used when Head Pose "
			"Method = Geometric).")
		scriptOp.par.Posepitchscale = POSE_PITCH_SCALE
		p = page.appendFloat('Posefocalscale', label='Head Pose Focal Scale (SolvePnP)', size=1)
		p[0].default = POSE_FOCAL_SCALE
		p[0].min = 0.1
		p[0].max = 5.0
		p[0].help = ("Multiplier on the assumed camera focal length (only used when Head Pose "
			"Method = SolvePnP) -- there's no real camera calibration available, so this is a "
			"stand-in meant to be tuned live against your actual camera/lens by comparing a real "
			"head turn to the displayed rotation.")
		scriptOp.par.Posefocalscale = POSE_FOCAL_SCALE
		p = page.appendFloat('Posesmoothing', label='Head Pose Smoothing', size=1)
		p[0].default = POSE_SMOOTHING
		p[0].min = 0.0
		p[0].max = 1.0
		p[0].clampMin = True
		p[0].clampMax = True
		p[0].help = ("Extra lerp on yaw/pitch/roll specifically (separate from Output Smoothing, "
			"which only smooths landmark/box position) -- deriving an angle from just 6 points "
			"amplifies real detection noise beyond what the already-smoothed landmarks show.")
		scriptOp.par.Posesmoothing = POSE_SMOOTHING
		p = page.appendToggle('Outputtrackdata', label='Output Track Data (Table)')
		p[0].default = True
		p[0].help = ("Whether to write per-frame face tracking + landmark summary data to "
			"table_output/table_landmarks at all. Pure performance toggle -- turn off if nothing "
			"downstream reads them.")
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
		p[0].help = object_tracker.par_help('Trackiouthreshold', subject='face', subject_plural='faces')
		scriptOp.par.Trackiouthreshold = TRACKER_IOU_THRESHOLD
		p = page.appendFloat('Trackconfirmframes', label='Track Confirm Frames', size=1)
		p[0].default = TRACKER_MIN_HITS
		p[0].min = 1.0
		p[0].max = 30.0
		p[0].clampMin = True
		p[0].clampMax = False
		p[0].help = object_tracker.par_help('Trackconfirmframes', subject='face', subject_plural='faces')
		scriptOp.par.Trackconfirmframes = TRACKER_MIN_HITS
		p = page.appendFloat('Outputsmoothing', label='Output Smoothing (Box + Landmarks)', size=1)
		p[0].default = OUTPUT_SMOOTHING
		p[0].min = 0.0
		p[0].max = 1.0
		p[0].clampMin = True
		p[0].clampMax = True
		p[0].help = object_tracker.par_help('Outputsmoothing', extra=(
			"Also smooths each tracked face's 468 landmark positions frame to frame (same "
			"value, same lerp), so per-frame landmark jitter is reduced."
		))
		scriptOp.par.Outputsmoothing = OUTPUT_SMOOTHING
		p = page.appendToggle('Drawdebug', label='Draw Debug Overlay')
		p[0].default = DRAW_BOXES
		p[0].help = ("Draws face box outlines + track id + landmark points on the output image. "
			"The main landmark visualization is the Debug COMP's geo instancing (driven by "
			"table_landmarks), not this overlay -- this is a lightweight secondary view.")
		scriptOp.par.Drawdebug = DRAW_BOXES

	def get_model_path(self):
		"""Return path to the BlazeFace detector model."""
		model_dir = os.path.join(project.folder, 'data', 'ml', 'mediapipe')
		return os.path.join(model_dir, DETECTOR_MODEL_FILENAME)

	def on_model_loaded(self, session):
		"""Log detector I/O and load the second (unthreaded) landmark session."""
		outputs = session.get_outputs()
		self.printONNX(f"MediaPipe face detector outputs ({len(outputs)}):")
		for o in outputs:
			self.printONNX(f"  name='{o.name}' shape={o.shape} type={o.type}")
		inputs = session.get_inputs()
		for inp in inputs:
			self.printONNX(f"  input name='{inp.name}' shape={inp.shape} type={inp.type}")
		self.check_providers(session)

		landmark_path = os.path.join(project.folder, 'data', 'ml', 'mediapipe', LANDMARK_MODEL_FILENAME)
		self._landmark_session = ort.InferenceSession(landmark_path, providers=onnx_inference_manager.providers())
		self.printONNX(f"Face landmark model loaded: {landmark_path}")
		self.printONNX(f"  Active providers: {self._landmark_session.get_providers()}")

	def preprocess(self, nA):
		"""Preprocess for BlazeFace. Assumes TD has already resized input to a SQUARE
		working resolution upstream (fit_square_sm, 'fill' stretch -- matching this
		model's own square training convention, unlike RVM's aspect-preserving resize).
		Regenerates anchors if the resolution changes (cheap: 896 anchors) -- unlike
		RVM's recurrent state, there's no error risk here from a stale anchor set, just
		silently wrong boxes, so this is a plain proactive regen, not a reset+retry."""
		self.original_h, self.original_w = nA.shape[:2]
		num_channels = nA.shape[2] if len(nA.shape) == 3 else 1

		needed = (1, 3, self.original_h, self.original_w)
		if self._input_buf_shape != needed:
			self._input_tensor_buf = np.empty(needed, dtype=np.float32)
			self._input_buf_shape = needed

		if self._anchor_input_size != self.original_w:
			# BASE_STRIDES are calibrated for a 128x128 input; scale proportionally to
			# whatever this network's actual working resolution is.
			scale_factor = self.original_w / 128.0
			strides = [int(round(s * scale_factor)) for s in BASE_STRIDES]
			self._anchors = _generate_anchors(self.original_w, strides)
			self._anchor_input_size = self.original_w
			self.printONNX(f"Regenerated {len(self._anchors)} anchors for {self.original_w}x{self.original_h}")

		if num_channels >= 3:
			flipped = nA[::-1, :, :3]  # flip V + drop alpha (view, no alloc)
		else:
			img = self.npu.flip_v(nA)
			flipped = self.npu.grayscale_to_rgb(img)

		# Kept for postprocess()'s per-face aligned-crop step -- see class docstring. A
		# real copy (not a view), since nA/flipped are TD-owned buffers not safe to hold
		# past this call.
		self._last_frame_rgb = np.ascontiguousarray(flipped, dtype=np.float32)

		# True (pre-square) source dimensions -- needed to correctly compute the rotation-
		# aligned landmark crop (see _run_landmarks_batch's docstring for why the square
		# buffer's own aspect-distorted pixel space can't be used directly for the
		# rotation step, unlike the plain axis-aligned box, whose fractional position/size
		# IS preserved under fit_square_sm's per-axis-uniform 'fill' stretch).
		try:
			src = self.scriptOp.parent().op('null_passthrough')
			self._true_w, self._true_h = src.width, src.height
		except Exception:
			self._true_w, self._true_h = self.original_w, self.original_h

		self._input_tensor_buf[0, 0] = flipped[:, :, 0]
		self._input_tensor_buf[0, 1] = flipped[:, :, 1]
		self._input_tensor_buf[0, 2] = flipped[:, :, 2]

		return self._input_tensor_buf

	def postprocess(self, outputs):
		"""Decode BlazeFace detections, track faces, run rotation-aligned landmark
		inference per tracked face (batched, fixed-size padded)."""
		if len(outputs) != 2:
			needed_shape = (self.original_h or 256, self.original_w or 256, 3)
			if self._output_buf is None or self._output_buf_shape != needed_shape:
				self._output_buf = np.zeros(needed_shape, dtype=np.float32)
				self._output_buf_shape = needed_shape
			return self.npu.flip_v(self._output_buf)

		input_w, input_h = self.original_w, self.original_h
		box_coords = outputs[0][0]           # (896, 16)
		box_scores = _sigmoid(outputs[1][0, :, 0])  # (896,)
		anchors = self._anchors

		self.conf_threshold = self._par_or_default('Confthreshold', CONF_THRESHOLD)
		self.low_conf_threshold = self._par_or_default('Lowconfthreshold', LOW_CONF_THRESHOLD)
		nms_iou_threshold = self._par_or_default('Nmsiouthreshold', NMS_IOU_THRESHOLD)
		min_box_width = self._par_or_default('Minboxwidth', MIN_BOX_WIDTH)
		min_box_height = self._par_or_default('Minboxheight', MIN_BOX_HEIGHT)
		roi_scale = self._par_or_default('Roiscale', ROI_SCALE)
		pose_method = self._par_or_default('Posemethod', POSE_METHOD)
		pose_yaw_scale = self._par_or_default('Poseyawscale', POSE_YAW_SCALE)
		pose_pitch_scale = self._par_or_default('Posepitchscale', POSE_PITCH_SCALE)
		pose_focal_scale = self._par_or_default('Posefocalscale', POSE_FOCAL_SCALE)
		pose_smoothing = self._par_or_default('Posesmoothing', POSE_SMOOTHING)
		self.tracker.high_thresh = self.conf_threshold
		self.tracker.low_thresh = self.low_conf_threshold
		self.tracker.match_thresh = self._par_or_default('Trackiouthreshold', TRACKER_IOU_THRESHOLD)
		self.tracker.track_buffer = self._par_or_default('Tracklossframes', TRACKER_MAX_AGE)
		self.tracker.min_hits = int(self._par_or_default('Trackconfirmframes', TRACKER_MIN_HITS))
		smoothing = self._par_or_default('Outputsmoothing', OUTPUT_SMOOTHING)

		# Box decode -- reverse_output_order=true in the original graph means the raw
		# layout is [x,y,w,h] (confirmed against tensors_to_detections_calculator.cc's
		# XYWH branch), scaled by input_size (fixed_anchor_size=true -> anchor.w/h=1, so
		# this simplifies to a plain offset+scale against the anchor center).
		box_scale = float(input_w)
		x_raw, y_raw, w_raw, h_raw = box_coords[:,0], box_coords[:,1], box_coords[:,2], box_coords[:,3]
		x_center = x_raw / box_scale * anchors[:,2] + anchors[:,0]
		y_center = y_raw / box_scale * anchors[:,3] + anchors[:,1]
		w = w_raw / box_scale * anchors[:,2]
		h = h_raw / box_scale * anchors[:,3]
		boxes_native = np.stack([x_center - w/2, y_center - h/2, x_center + w/2, y_center + h/2], axis=-1)

		keypoints = []
		for k in range(NUM_KEYPOINTS):
			off = 4 + k * 2
			kx = box_coords[:,off] / box_scale * anchors[:,2] + anchors[:,0]
			ky = box_coords[:,off+1] / box_scale * anchors[:,3] + anchors[:,1]
			keypoints.append(np.stack([kx, ky], axis=-1))
		keypoints = np.stack(keypoints, axis=1)  # (896, 6, 2), normalized, native orientation

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

		# Isotropic box-SIZE correction (see Bug 3 in
		# docs/learnings/debug-comp-camera-aspect.md). This model's fixed_anchor_size=true
		# box regression always outputs w_raw==h_raw in square-buffer terms, i.e. it
		# assumes a square box in its own square input space. Naively reprojecting that by
		# multiplying width by true_w and height by true_h independently is valid for
		# POSITION (fraction-of-square == fraction-of-true-frame under fit_square_sm's
		# 'fill' stretch) but bakes the true frame's own aspect ratio into every box's
		# SIZE, since w_fraction == h_fraction by construction. Fix: treat the model's
		# single size value as an ISOTROPIC true-pixel size (same absolute pixel size on
		# both axes), then re-express as a fraction of each axis's own true dimension.
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

		# Flip Y-axis for TouchDesigner (model uses top-down, TD uses bottom-up)
		boxes_td = boxes_native_iso.copy()
		boxes_td[:, 1], boxes_td[:, 3] = 1.0 - boxes_td[:, 3], 1.0 - boxes_td[:, 1]

		detections = []
		for i in range(len(boxes_td)):
			detections.append({
				'box': boxes_td[i].tolist(),
				'score': float(scores_valid[i]),
				# native (pre-flip) box + eye keypoints kept for the aligned-crop step
				'box_native': boxes_native[i].tolist(),
				'eyes_native': kps_valid[i, :2].tolist(),  # [right_eye, left_eye]
			})

		active_tracks = self.tracker.update(detections)

		# Pass 1: box smoothing + collect each confirmed track's native-space box/eyes,
		# but DON'T run the landmark model yet -- collected first so every face can be
		# batched into ONE call below (see MAX_BATCH_FACES).
		confirmed = []
		for t in active_tracks:
			if t.score < self.conf_threshold or not t.confirmed:
				continue
			box = t.box  # Kalman estimate (TD-flipped orientation)
			smoothed = object_tracker.box_smooth(self._box_state, t.track_id, box, smoothing)

			box_native = t.payload.get('box_native')
			eyes_native = t.payload.get('eyes_native')
			if box_native is None or eyes_native is None:
				# Lost-but-confirmed track (Kalman-predicted only, no fresh detection) --
				# flip the smoothed TD-space box back to native rather than skip landmark
				# inference entirely, so a briefly-occluded face still gets a held reading.
				x1, y1_td, x2, y2_td = smoothed
				box_native = [x1, 1.0 - y2_td, x2, 1.0 - y1_td]
				eyes_native = None  # can't recover a rotation angle -- fall back to axis-aligned
			confirmed.append({'track': t, 'smoothed': smoothed, 'box_native': box_native, 'eyes_native': eyes_native})

		if confirmed:
			batch_results = self._run_landmarks_batch(confirmed, roi_scale)
			for c, landmarks in zip(confirmed, batch_results):
				if landmarks is None:
					continue
				track_id = c['track'].track_id
				prev = self._landmark_state.get(track_id)
				self._landmark_state[track_id] = (
					landmarks if prev is None
					else prev * smoothing + landmarks * (1.0 - smoothing)
				)

				# Head pose (yaw/pitch/roll) -- derived from the SAME 468 smoothed
				# landmarks just computed, not a separate model call. See the module's
				# HEAD POSE section for POSE_LANDMARK_INDICES/method details. Landmarks
				# are TD-space normalized (x, y_td, z) -- undo the y-flip and scale by
				# TRUE frame dimensions to get native pixel coords, matching
				# onnx_yunet.py's own solvepnp function's input convention and this
				# script's other true-pixel-space fixes.
				lm = self._landmark_state[track_id]
				true_w = self._true_w or self.original_w
				true_h = self._true_h or self.original_h
				pose_pts = {}
				for name, idx in zip(
					('nose', 'chin', 'eye_r', 'eye_l', 'mouth_r', 'mouth_l'),
					POSE_LANDMARK_INDICES,
				):
					lx, ly_td, _ = lm[idx]
					pose_pts[name] = (lx * true_w, (1.0 - ly_td) * true_h)

				if pose_method == 'solvepnp':
					yaw, pitch, roll = _compute_head_direction_solvepnp(
						pose_pts, true_w, true_h, pose_focal_scale)
				else:
					yaw, pitch, roll = _compute_head_direction_geometric(
						pose_pts, pose_yaw_scale, pose_pitch_scale)

				prev_pose = self._pose_state.get(track_id)
				if prev_pose is None:
					self._pose_state[track_id] = {'yaw': yaw, 'pitch': pitch, 'roll': roll}
				else:
					self._pose_state[track_id] = {
						'yaw': prev_pose['yaw'] * pose_smoothing + yaw * (1.0 - pose_smoothing),
						'pitch': prev_pose['pitch'] * pose_smoothing + pitch * (1.0 - pose_smoothing),
						'roll': prev_pose['roll'] * pose_smoothing + roll * (1.0 - pose_smoothing),
					}

		self.tracked_objects = []
		for c in confirmed:
			t = c['track']
			smoothed = c['smoothed']
			held_landmarks = self._landmark_state.get(t.track_id)
			held_pose = self._pose_state.get(t.track_id, {'yaw': 0.0, 'pitch': 0.0, 'roll': 0.0})

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
				'landmarks': held_landmarks,  # (468,3) TD-space normalized, or None
				'yaw': held_pose['yaw'], 'pitch': held_pose['pitch'], 'roll': held_pose['roll'],
			})

		active_ids = {t.track_id for t in active_tracks}
		object_tracker.prune_stale(active_ids, self._box_state, self._landmark_state, self._pose_state)

		if DRAW_BOXES:
			output_img = self.npu.flip_v(self.draw_tracked_faces())
		else:
			# Black frame -- no need to allocate/draw/flip/color-convert every frame when
			# the overlay is off, just reuse a static cached buffer (same pattern as the
			# no-detector-output-yet branch above, and every other onnx_*.py script's
			# Drawdebug handling). The REAL landmark visualization is the Debug COMP's geo
			# instancing driven by table_landmarks, unaffected by this toggle either way.
			needed_shape = (self.original_h or 256, self.original_w or 256, 3)
			if self._output_buf is None or self._output_buf_shape != needed_shape:
				self._output_buf = np.zeros(needed_shape, dtype=np.float32)
				self._output_buf_shape = needed_shape
			output_img = self._output_buf
		return output_img

	def on_result_published(self):
		"""Flush table_output/table_landmarks from tracked_objects right after this
		frame's texture publishes, before the next frame's capture/dispatch -- see
		ONNXInferenceManager.on_result_published()'s docstring. Gated by Outputtrackdata,
		same reasoning as onnx_yolo26_seg.py's identical method."""
		if self._par_or_default('Outputtrackdata', True):
			self.write_tracks_to_table()
			self.write_landmarks_to_table()

	def _run_landmarks_batch(self, confirmed, roi_scale):
		"""Extract each confirmed face's own rotation-aligned crop (via its own affine
		transform, using the eye keypoints -- see class docstring) and run the landmark
		model once per face. Unlike HSEmotion's emotion classifier, face_landmark_detector
		.onnx has a FIXED batch-1 input ([1,3,192,192]), so there's no MAX_BATCH_FACES-style
		padding to do here -- every call uses the exact same shape regardless of face count,
		so ORT's CUDA algorithm-search cache (see MAX_BATCH_FACES's own comment / Round 5 in
		.ai/skills/td-threaded-inference-optimization.md) is never invalidated in the first
		place. Each face's 468 output landmarks are mapped back through the INVERSE of its
		own affine into original-frame TD-space normalized coordinates. Returns a list the
		same length as `confirmed`, each either a (468,3) array or None.

		IMPORTANT -- works in TRUE (pre-square) pixel units for the rotation/scale/center
		math, not the square working buffer's own pixel units. `fit_square_sm`'s 'fill'
		stretch is a per-axis scale that differs between axes, so a fraction computed in
		square-space equals the same fraction in true-space for POSITION (the per-axis
		scales cancel out of the ratio), but not for SIZE or ROTATION -- see Bugs 2 and 3
		in docs/learnings/debug-comp-camera-aspect.md for the full derivation of why the
		isotropic size fix below is needed and why rotating in the anisotropically
		stretched square-pixel grid introduces real shear.

		Fix: build the crop's rotation+scale+translate matrix entirely in TRUE-pixel
		terms (correct rotation angle, correct box center/size), then compose it with the
		square<->true "undistort" diagonal scale matrix D so the final affine still
		operates directly on the square buffer's own pixel data (the actual image
		content) for cv2.warpAffine -- and correspondingly map the inverse result back
		through D before normalizing to true-frame fractions for output.
		"""
		results = [None] * len(confirmed)
		frame = self._last_frame_rgb
		if frame is None or self._landmark_session is None or not confirmed:
			return results
		square_h, square_w = frame.shape[:2]
		true_w = self._true_w or square_w
		true_h = self._true_h or square_h
		# D: true-pixel = D @ square-pixel (per-axis "undistort" scale)
		dx_factor = true_w / square_w
		dy_factor = true_h / square_h

		if len(confirmed) > MAX_BATCH_FACES:
			self.printONNX(
				f"WARNING: {len(confirmed)} faces this frame exceeds MAX_BATCH_FACES="
				f"{MAX_BATCH_FACES} -- landmarking only the first {MAX_BATCH_FACES}."
			)

		true_aspect = true_w / true_h
		iso_sqrt_aspect = math.sqrt(true_aspect)

		for i, c in enumerate(confirmed[:MAX_BATCH_FACES]):
			box_native = c['box_native']
			eyes_native = c['eyes_native']
			# box_native is a normalized SQUARE-space fraction; fraction-of-square ==
			# fraction-of-true for plain axis-aligned POSITION, so the center is correct
			# as-is. SIZE needs the same isotropic true-pixel correction as the
			# output-facing box fix above (Bug 3 in
			# docs/learnings/debug-comp-camera-aspect.md) -- otherwise the crop would be
			# oversized on whichever axis the source frame is wider on.
			x1, y1, x2, y2 = box_native[0]*true_w, box_native[1]*true_h, box_native[2]*true_w, box_native[3]*true_h
			box_cx, box_cy = (x1+x2)/2, (y1+y2)/2
			box_w_sq_frac = box_native[2] - box_native[0]
			box_h_sq_frac = box_native[3] - box_native[1]
			iso_w = box_w_sq_frac * true_w / iso_sqrt_aspect
			iso_h = box_h_sq_frac * true_h * iso_sqrt_aspect
			box_w, box_h = iso_w, iso_h
			if box_w <= 0 or box_h <= 0:
				continue

			if eyes_native is not None:
				re, le = eyes_native
				dx = (le[0] - re[0]) * true_w
				dy = (le[1] - re[1]) * true_h
				angle_rad = math.atan2(dy, dx)
			else:
				angle_rad = 0.0

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
			chw = aligned.transpose(2, 0, 1).astype(np.float32)[np.newaxis, ...]  # (1,3,192,192)

			A_inv = np.linalg.inv(A)
			t_inv = -A_inv @ t_vec

			lmk_out = self._landmark_session.run(None, {'image': chw})
			lm = lmk_out[1][0]  # (468, 3), x/y NORMALIZED 0-1 relative to the 192x192 crop
			# (NOT pixel-range 0-192 -- must be multiplied by LANDMARK_INPUT_SIZE below
			# before the inverse affine, or all 468 points collapse to a single sub-pixel
			# cluster. z comes out already small/relative with no documented unit from
			# MediaPipe, so it's left as raw model output.)

			xy_crop = lm[:, :2] * LANDMARK_INPUT_SIZE  # normalized -> crop-space pixels
			# A_inv maps crop-space pixels directly back to SQUARE-pixel space (since A
			# was built to operate on square-pixel input) -- but square-pixel position is
			# NOT fraction-equivalent to true-pixel position for a point that went through
			# the rotation step, so this must go back through D before normalizing.
			square_xy = (A_inv @ xy_crop.T).T + t_inv  # (468, 2) square-pixel space
			true_xy = square_xy * np.array([dx_factor, dy_factor])  # -> true-pixel space
			x_norm = true_xy[:, 0] / true_w
			y_norm_native = true_xy[:, 1] / true_h
			y_norm_td = 1.0 - y_norm_native  # flip to TD's bottom-up convention
			z_norm = lm[:, 2]
			results[i] = np.stack([x_norm, y_norm_td, z_norm], axis=-1).astype(np.float32)

		return results

	def draw_tracked_faces(self):
		"""Lightweight debug view at the detector's native working resolution -- box
		outlines + track id + landmark points. The main landmark visualization is the
		Debug COMP's geo instancing driven by table_landmarks, not this (see Drawdebug
		par help). Gated entirely behind DRAW_BOXES at the postprocess() call site
		(skipped, not just drawn empty, when off); this method itself always draws."""
		proto_h, proto_w = self.original_h or 256, self.original_w or 256
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
			cv2.putText(draw_img, f"#{obj['track_id']} yaw={obj['yaw']:+.0f}deg", (px1, max(py_top - 6, 12)),
				cv2.FONT_HERSHEY_SIMPLEX, 0.5, color_bgr, 1, cv2.LINE_AA)
			if obj['landmarks'] is not None:
				for lx, ly, _ in obj['landmarks']:
					px, py = to_px(lx, ly)
					if 0 <= px < proto_w and 0 <= py < proto_h:
						draw_img[py, px] = color_bgr

		return cv2.cvtColor(draw_img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0

	# ==================== CHOP TRACKING OUTPUT ====================
	# To output tracking data to a CHOP, use a Script CHOP DAT with:
	#
	#   mgr = op('script1').module.inference_manager
	#   tracks = mgr.tracked_objects  # list of dicts
	#
	# Each dict contains: track_id, score, cx, cy, w, h, x_left, x_right, y_top,
	#   y_bottom, vx, vy (Kalman-estimated), lost_frames, total_frames,
	#   landmarks (shape (468,3) TD-space normalized array, or None)

	def write_tracks_to_table(self):
		"""Per-track summary Table DAT (one row per tracked face)."""
		tbl = self.opOutputTableDAT
		if tbl is None:
			return
		tbl.clear()
		# yaw/pitch/roll are all in DEGREES, but exactly how "real" depends on Posemethod
		# -- see _compute_head_direction_geometric()/_compute_head_direction_solvepnp()'s
		# docstrings. yaw = left/right turn, pitch = nod, roll = tilt (a genuine angle
		# either way). Same data-output scheme as onnx_yunet.py's own table_output.
		tbl.appendRow([
			*object_tracker.label_header(),
			*object_tracker.box_header(),
			'yaw', 'pitch', 'roll',
			*object_tracker.color_header(),
		])
		for obj in self.tracked_objects:
			tbl.appendRow([
				*object_tracker.label_row(obj['track_id'], obj['score']),
				*object_tracker.box_row(obj),
				f"{obj['yaw']:.4f}", f"{obj['pitch']:.4f}", f"{obj['roll']:.4f}",
				*object_tracker.color_row(obj['track_id']),
			])

	def write_landmarks_to_table(self):
		"""Flat per-visible-landmark Table DAT, one row per landmark across ALL tracked
		faces -- shared table_joints schema, see object_tracker.joints_header()'s
		docstring (no fixed per-face/per-landmark slot layout, so there's no cap on how
		many faces get instanced at once downstream). The 468-point mesh has no named
		joints or per-point confidence, so 'name' is the point's own index and 'conf' is
		a constant 1.0 stand-in."""
		tbl = self.opJointsTableDAT
		if tbl is None:
			return
		tbl.clear()
		tbl.appendRow(object_tracker.joints_header())
		for obj in self.tracked_objects:
			if obj['landmarks'] is None:
				continue
			track_id = obj['track_id']
			for idx, (lx, ly, lz) in enumerate(obj['landmarks']):
				tbl.appendRow(object_tracker.joints_row(track_id, str(idx), lx, ly, lz, 1.0))


# Create global instance -- shut down any PREVIOUS instance first (releases its
# GPU-resident ONNX Runtime session(s) and stops its worker thread) so a script
# reload during active development doesn't leak both -- see
# onnx_inference_manager.shutdown_and_register()'s docstring for the full
# mechanism this avoids (and why it's NOT TD's own store()/fetch(), which risked
# a real crash trying to persist a live, unpicklable manager instance).
inference_manager = MediaPipeFaceInference()
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
	"""See onnx_yolo26_seg.py's identical method for why this is unconditionally ALWAYS
	rather than AUTOMATIC."""
	return CookLevel.ALWAYS
