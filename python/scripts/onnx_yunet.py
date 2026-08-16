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
ByteTracker = object_tracker.ByteTracker

# ==================== CONFIGURATION ====================
# YuNet's own facial keypoints (fixed by the model, not configurable): right eye, left
# eye, nose tip, right mouth corner, left mouth corner.
NUM_KEYPOINTS = 5
KEYPOINT_NAMES = ['eye_r', 'eye_l', 'nose', 'mouth_r', 'mouth_l']

# Confidence threshold for a detected face to be shown/tracked (0.0 - 1.0). This is
# ByteTracker's "high confidence" threshold -- detections at or above this score are
# matched first and can start brand-new tracks. YuNet's own scores run fairly high for
# real faces, unlike e.g. onnx_yolo26_pose.py's degenerate low-confidence scene.
CONF_THRESHOLD = 0.7

# ByteTracker's "low confidence" threshold. Detections scoring between this and
# CONF_THRESHOLD are never used to start a new track, but ARE used in a second
# association pass to recover existing tracks that a plain confidence-thresholded
# detector would otherwise drop (occlusion, motion blur, partial visibility, head turn).
LOW_CONF_THRESHOLD = 0.3

# Minimum box width/height (normalized 0-1, fraction of frame dimension) for a detection
# to be kept at all -- applied alongside Confthreshold, before NMS/tracking. Separate
# width/height floors, NOT one shared value -- see the identical comment in
# onnx_yolo26_pose.py/onnx_yolo26_obj_det.py for why a single shared threshold ends up
# rejecting real, legitimately-large-but-narrow detections once tuned high enough to
# reject noise.
MIN_BOX_WIDTH = 0.02
MIN_BOX_HEIGHT = 0.02

# Tracker: max frames to keep a lost track alive. Faces are prone to brief full
# occlusion (head turn, hand pass, walking behind something) more than a general object
# detector's targets, hence the longer buffer than onnx_yolo26_obj_det.py's default.
TRACKER_MAX_AGE = 45

# Tracker: min IoU to accept a match between a track and a detection.
TRACKER_IOU_THRESHOLD = 0.2

# Tracker: total matched frames (not necessarily consecutive -- see object_tracker.Track's
# confirmed/hits) a brand-new track needs before it's confirmed and shown/output at all.
# Cuts down on single-frame noise "detections" registering as a real face -- almost none
# of that noise ever gets a second real match at all before track_buffer prunes it.
TRACKER_MIN_HITS = 3

# Smoothing factor for box position/size lerp (0 = no smoothing, 1 = frozen). Same role
# as Outputsmoothing in onnx_yolo26_obj_det.py -- ByteTracker's Kalman filter already
# smooths motion prediction, this adds an extra lerp on top of the matched-detection
# snap. Kept lower than onnx_yolo26_obj_det.py's default since a face's own motion
# (head turns) reads as less natural with heavy smoothing.
OUTPUT_SMOOTHING = 0.3

# Which head-pose method to use -- see _compute_head_direction_geometric() (default,
# keypoint-distance-ratio heuristic, no solver) vs _compute_head_direction_solvepnp()
# (3D model + cv2.solvePnP, kept available behind this flag). Geometric is the default:
# far less jittery, since it's bounded distance ratios rather than an ill-conditioned
# 6-DOF solve over 5 sparse near-planar points.
POSE_METHOD = 'geometric'  # or 'solvepnp'

# Degrees-per-ratio scale for the geometric method's yaw/pitch, SEPARATE for each axis
# -- see _compute_head_direction_geometric()'s docstring for why one shared scale
# doesn't work (yaw's and pitch's ratios cover very different natural ranges for the
# same real rotation angle). Tune live: calibrated against each ratio's own observed
# range for a realistic head turn, not against a theoretical +-1 bound.
POSE_YAW_SCALE = 340.0
POSE_PITCH_SCALE = 100.0

# Multiplier on the assumed camera focal length used only by the solvepnp method -- see
# _compute_head_direction_solvepnp's focal_scale doc. No real camera calibration
# available, so this is a stand-in meant to be tuned live: it's the single biggest
# source of scale error in that method's derived rotation (wrong focal length directly
# biases how large a rotation the solve thinks is needed to explain a given 2D keypoint
# displacement).
POSE_FOCAL_SCALE = 1.0

# Smoothing factor for yaw/pitch/roll specifically -- separate from OUTPUT_SMOOTHING,
# which only smooths box position/size. Applies regardless of which Posemethod is
# active -- both methods' raw per-frame angles can be visibly jittery even when
# genuinely holding still (the geometric method less so, but not immune -- keypoint
# noise is keypoint noise). Higher = smoother but more lag following a real head turn.
POSE_SMOOTHING = 0.5

# Draw boxes/keypoints on the output image?
DRAW_BOXES = False

BOX_COLOR_BGR = (0, 255, 0)      # Green
KEYPOINT_COLOR_BGR = (0, 128, 255)  # Orange


# Rough canonical 3D face model (average adult proportions, NOT subject-specific --
# solvePnP only needs plausible relative proportions to recover orientation, not exact
# measurements) matched 1:1 against YuNet's 5 keypoints. Face-centered coordinate frame
# deliberately matches OpenCV's camera-space convention (X = right, Y = DOWN, Z = away
# from camera), not a "natural" Y-up convention: with Y-up, the (0,0,0) "facing camera"
# initial guess below would actually correspond to upside-down (identity rotation maps
# model axes straight onto camera axes), pulling every solve toward a ~180-degree-pitch
# local optimum. With Y-down, identity rotation genuinely means "upright, facing camera."
#
# Depth (Z) values are intentionally modest relative to the eye/mouth spread (~63mm
# interpupillary distance, nose protruding only ~10-15mm forward of the eye/mouth plane).
# Exaggerating them makes yaw specifically (the axis most dependent on correctly
# interpreting depth from a near-planar point set) badly over/under-sensitive, while
# roll (nearly depth-independent -- basically just the 2D eye-line slope) is unaffected.
_HEAD_MODEL_POINTS = np.array([
	(-31.5, -20.0, -10.0),  # right eye
	( 31.5, -20.0, -10.0),  # left eye
	(  0.0,   0.0,   0.0),  # nose tip (most forward point -- the origin)
	(-25.0,  25.0, -12.0),  # right mouth corner
	( 25.0,  25.0, -12.0),  # left mouth corner
], dtype=np.float64)


def _rotation_matrix_to_euler(R):
	"""Rotation matrix -> (pitch, yaw, roll) in radians, extrinsic X-Y-Z (Tait-Bryan)
	decomposition -- the standard convention used across OpenCV head-pose tutorials."""
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


def _compute_head_direction_geometric(keypoints, yaw_scale=340.0, pitch_scale=100.0):
	"""Estimate head yaw/pitch/roll from keypoint GEOMETRY directly, no 3D model or
	solver involved -- the alternative to _compute_head_direction_solvepnp() below,
	switchable via the Posemethod par (this is the default). Uses bounded distance
	RATIOS between the nose and the other 4 keypoints rather than solving a 6-DOF pose
	from 5 sparse points, so it's far less sensitive to keypoint noise (no ill-
	conditioned optimization, no near-planar flip ambiguity). Not a calibrated
	real-world angle, so each ratio is mapped to degrees via its own tunable linear
	scale (Poseyawscale/Posepitchscale) rather than a single shared one: yaw's and
	pitch's ratios cover very different natural ranges for the same real rotation
	(yaw barely reaches ~0.13 at a true 45 degree turn, pitch reaches ~0.45-0.56 at a
	true 45 degree nod), so one shared scale would badly under-drive yaw specifically.

	Yaw: as the head turns, the nose visually moves toward the near-side eye/mouth
	  corner and away from the far side -- (nose-to-right distances) vs (nose-to-left
	  distances), summed across both eye and mouth for noise-averaging, turned into a
	  ratio and scaled to degrees. The ratio saturates well before +-1 in practice (a
	  real face is only reliably detectable up to some self-occlusion limit, the far
	  corner vanishing, well before the mathematical 90 degrees) -- Poseyawscale is
	  calibrated against the ratio's actual observed range, not a theoretical +-1 bound.
	Pitch: identical idea, vertically -- nose distance to the eye-line vs the mouth-line.
	  Has a small inherent baseline offset even at a neutral pose (real faces aren't
	  perfectly symmetric top/bottom around the nose -- the mouth typically sits farther
	  from the nose than the eyes do), left uncorrected since the right baseline varies
	  per-face/per-camera-setup and hardcoding one measured against a synthetic model
	  risks being wrong for a real face.
	Roll: eye-line tilt -- already a genuine, robust real angle, same as the solvePnP
	  version's roll below.

	Returns (0.0, 0.0, 0.0) if keypoints are missing/degenerate.
	"""
	if not keypoints or len(keypoints) < NUM_KEYPOINTS:
		return 0.0, 0.0, 0.0

	eye_r = np.array(keypoints[0])
	eye_l = np.array(keypoints[1])
	nose = np.array(keypoints[2])
	mouth_r = np.array(keypoints[3])
	mouth_l = np.array(keypoints[4])

	dist_r = np.linalg.norm(nose - eye_r) + np.linalg.norm(nose - mouth_r)
	dist_l = np.linalg.norm(nose - eye_l) + np.linalg.norm(nose - mouth_l)
	# (dist_r - dist_l), NOT (dist_l - dist_r) -- a positive real yaw must produce a
	# positive ratio here; the reversed order gives the opposite sign.
	yaw_ratio = (dist_r - dist_l) / max(dist_l + dist_r, 1e-6)

	eye_mid = (eye_r + eye_l) * 0.5
	mouth_mid = (mouth_r + mouth_l) * 0.5
	dist_eyes = np.linalg.norm(nose - eye_mid)
	dist_mouth = np.linalg.norm(nose - mouth_mid)
	# (dist_eyes - dist_mouth), NOT (dist_mouth - dist_eyes) -- sign matters here the
	# same way it does for yaw_ratio above.
	pitch_ratio = (dist_eyes - dist_mouth) / max(dist_mouth + dist_eyes, 1e-6)

	dx = eye_l[0] - eye_r[0]
	dy = eye_l[1] - eye_r[1]
	roll = math.degrees(math.atan2(dy, dx))

	yaw_ratio = max(-1.0, min(1.0, yaw_ratio))
	pitch_ratio = max(-1.0, min(1.0, pitch_ratio))
	return yaw_ratio * yaw_scale, pitch_ratio * pitch_scale, roll


def _compute_head_direction_solvepnp(keypoints, width, height, focal_scale=1.0):
	"""Estimate real 3D head rotation -- yaw, pitch, roll, all in DEGREES -- from the 5
	facial keypoints (TD-normalized coords) via cv2.solvePnP. Matches the 5 detected
	keypoints against _HEAD_MODEL_POINTS (a rough canonical 3D face, not subject-specific)
	using an approximate camera intrinsic matrix -- a genuine, if approximate, 3D
	orientation estimate, directly usable for driving an actual 3D rotation (e.g. a
	cube's ry to visualize head turn), unlike _compute_head_direction_geometric()'s
	unitless ratios. cv2.solvePnP on this few points is a cheap numerical solve (not a
	model inference) -- negligible cost next to the detector itself.

	focal_scale: multiplier on the assumed focal length (focal_length = width *
	  focal_scale) -- there's no real camera calibration available, so this is a
	  standard stand-in, and the single biggest source of scale error (wrong focal
	  length directly biases how large a rotation the solve thinks is needed to explain
	  a given 2D keypoint displacement). Exposed as a tunable par (Posefocalscale)
	  specifically so it can be calibrated live against your actual camera/lens by
	  comparing a real head turn to the displayed rotation, rather than guessed once
	  and left wrong.

	yaw = rotation about the vertical axis -- left/right head turn (this is what you
	  want for e.g. a cube's Y-rotation).
	pitch = rotation about the horizontal axis -- up/down head tilt/nod.
	roll = rotation about the depth axis -- ear-to-shoulder tilt (matches the old
	  heuristic's roll closely, since that one was already a real angle).

	Returns (0.0, 0.0, 0.0) if keypoints are missing or the solve fails.
	"""
	if not keypoints or len(keypoints) < NUM_KEYPOINTS:
		return 0.0, 0.0, 0.0

	# Undo TD's normalization/Y-flip to get back to standard image-space pixel coords
	# (origin top-left, Y down) that cv2.solvePnP expects.
	image_points = np.array([
		(kx * width, (1.0 - ky) * height) for kx, ky in keypoints[:NUM_KEYPOINTS]
	], dtype=np.float64)

	focal_length = width * focal_scale
	center = (width / 2.0, height / 2.0)
	camera_matrix = np.array([
		[focal_length, 0.0, center[0]],
		[0.0, focal_length, center[1]],
		[0.0, 0.0, 1.0],
	], dtype=np.float64)
	dist_coeffs = np.zeros((4, 1))

	# ITERATIVE with an explicit extrinsic guess, NOT the default DLT-based init (needs
	# >=6 points, fails on YuNet's 5) and NOT a bare EPNP call either -- EPNP alone can
	# pick a wildly wrong solution (e.g. pitch ~162 degrees, "facing away and upside
	# down"), a real flip ambiguity inherent to near-planar point sets like a face (two
	# very different rotations can project to nearly the same 2D points). Seeding with
	# a plausible "facing the camera, at a reasonable distance" guess and refining via
	# Levenberg-Marquardt converges to the physically sensible solution instead, and
	# incidentally sidesteps ITERATIVE's 6-point minimum (which only applies to its own
	# internal DLT initialization, bypassed by the explicit guess).
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
	return math.degrees(yaw), math.degrees(pitch), math.degrees(roll)


# ==================== YUNET FACE DETECTION ====================

class YuNetInference(ONNXInferenceManager):
	"""YuNet face detection inference with temporal tracking, modernized to match
	onnx_yolo26_obj_det.py's structure/output schema as closely as possible (single-
	"class" detector, so no class_id/class_name columns, but every other column name
	matches -- the existing Debug view's geo/select nodes read table_output by column
	name and need no changes).

	YuNet is NOT a raw ONNX Runtime model in this codebase -- it's OpenCV's own
	cv2.FaceDetectorYN wrapper (which loads the same .onnx file internally via OpenCV's
	DNN module, not onnxruntime). That means the base class's model-loading method
	(written specifically for ort.InferenceSession) doesn't apply, so this subclass
	overrides _load_model_thread() directly rather than using get_session_options()/
	on_model_loaded() the way the other scripts do. run_inference() (called from the
	base class's own _worker_loop(), which handles timing/locking/exceptions) is still
	the right override point for the per-frame detect() call, same as every other
	script's custom-session override (see onnx_rvm_seg.py). Every other base class
	contract (threading model, onCook flow, self.session/is_loading/load_error
	semantics, play/pause skip, perf tracking) is preserved unchanged.

	Tracking uses `object_tracker.ByteTracker` (shared across every ONNX script in this
	project) for the full box-tracking lifecycle -- Kalman motion prediction, optimal
	(Hungarian) assignment, and ByteTrack's two-stage high/low-confidence association.
	Box position/size is smoothed on top of the tracker's own Kalman estimate
	(self._box_state), the same role Outputsmoothing plays in onnx_yolo26_obj_det.py.
	Facial keypoints and head direction (yaw/pitch/roll -- see Posemethod: either
	_compute_head_direction_geometric()'s keypoint-distance-ratio heuristic (default) or
	_compute_head_direction_solvepnp()'s 3D-model solve) are the face-specific extras
	this model provides beyond a generic box detector. Keypoints are positions, same as
	the box, so they're smoothed the same way (Outputsmoothing) rather than left raw --
	held at their last smoothed value across lost frames rather than reset, same
	reasoning as onnx_yolo26_pose.py's own keypoint hold logic. Head direction gets its
	OWN separate smoothing on top (Posesmoothing) -- deriving an angle from just 5
	sparse keypoints amplifies real detection noise more than the (already-smoothed)
	keypoints themselves visibly show (worse for solvepnp than geometric, but present in
	both), so the derived angles need their own additional damping regardless of method.
	"""

	def __init__(self):
		super().__init__()
		self.opOutputTableDAT = parent().op('table_output')  # Optional Table DAT for structured output
		self.opJointsTableDAT = parent().op('table_joints')
		self.conf_threshold = CONF_THRESHOLD  # Will be overridden by custom par
		self.low_conf_threshold = LOW_CONF_THRESHOLD
		self.tracker = ByteTracker(
			high_thresh=CONF_THRESHOLD, low_thresh=LOW_CONF_THRESHOLD,
			match_thresh=TRACKER_IOU_THRESHOLD, track_buffer=TRACKER_MAX_AGE,
			min_hits=TRACKER_MIN_HITS,
		)
		# Per-track box position/size smoothing state, keyed by track_id (see
		# OUTPUT_SMOOTHING comment -- layered on top of ByteTracker's own Kalman estimate).
		self._box_state = {}
		# Per-track held keypoints + head direction, keyed by track_id -- updated only
		# on a fresh match (lost_frames == 0), held across predicted-only frames
		# otherwise, same reasoning as onnx_yolo26_pose.py's _kpt_state.
		self._kpt_state = {}
		# Structured tracking data exposed for CHOP/table consumption
		self.tracked_objects = []
		# YuNet needs setInputSize() called whenever the actual input dimensions change
		# (it's a variable-input-resolution architecture, unlike the fixed-640 YOLO
		# models) -- cached so we only call it on an actual change, not every frame.
		self._cached_input_size = None
		# Pre-allocated black-frame buffer (see postprocess()'s DRAW_BOXES-off path)
		self._output_buf = None
		self._output_buf_shape = None

	def onSetupParameters(self, scriptOp):
		"""Add YuNet-specific parameters alongside base class params."""
		super().onSetupParameters(scriptOp)
		page = scriptOp.appendCustomPage('YuNet')
		p = page.appendFloat('Confthreshold', label='Confidence Threshold', size=1)
		p[0].default = CONF_THRESHOLD
		p[0].min = 0.0
		p[0].max = 1.0
		p[0].clampMin = True
		p[0].clampMax = True
		p[0].help = object_tracker.par_help('Confthreshold', extra=(
			"YuNet's own scores for real faces run fairly high (0.7-0.9+ typical)."
		))
		scriptOp.par.Confthreshold = CONF_THRESHOLD
		p = page.appendFloat('Lowconfthreshold', label='Low Confidence Threshold (Recovery)', size=1)
		p[0].default = LOW_CONF_THRESHOLD
		p[0].min = 0.0
		p[0].max = 1.0
		p[0].clampMin = True
		p[0].clampMax = True
		p[0].help = object_tracker.par_help('Lowconfthreshold')
		scriptOp.par.Lowconfthreshold = LOW_CONF_THRESHOLD
		p = page.appendFloat('Minboxwidth', label='Min Box Width', size=1)
		p[0].default = MIN_BOX_WIDTH
		p[0].min = 0.0
		p[0].max = 0.2
		p[0].clampMin = True
		p[0].clampMax = False
		p[0].help = object_tracker.par_help('Minboxwidth', shape_note=(
			"a face is rarely square, so one shared threshold high enough to reject noise ends up "
			"rejecting real faces that are just proportionally narrow (e.g. a turned head)."
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
		p = page.appendFloat('Tracklossframes', label='Track Loss Frames', size=1)
		p[0].default = TRACKER_MAX_AGE
		p[0].min = 0.0
		p[0].max = 90.0
		p[0].clampMin = True
		p[0].clampMax = False
		p[0].help = object_tracker.par_help('Tracklossframes', extra=(
			"Kept longer than the other scripts' default here since faces are especially prone to "
			"brief full occlusion (head turn, hand pass) where NO detection fires at all, unlike a "
			"body/box detector that often still gets a degraded read through partial occlusion."
		))
		scriptOp.par.Tracklossframes = TRACKER_MAX_AGE
		p = page.appendFloat('Trackiouthreshold', label='Track IoU Threshold', size=1)
		p[0].default = TRACKER_IOU_THRESHOLD
		p[0].min = 0.0
		p[0].max = 1.0
		p[0].clampMin = True
		p[0].clampMax = True
		p[0].help = object_tracker.par_help('Trackiouthreshold', subject='face')
		scriptOp.par.Trackiouthreshold = TRACKER_IOU_THRESHOLD
		p = page.appendFloat('Trackconfirmframes', label='Track Confirm Frames', size=1)
		p[0].default = TRACKER_MIN_HITS
		p[0].min = 1.0
		p[0].max = 30.0
		p[0].clampMin = True
		p[0].clampMax = False
		p[0].help = object_tracker.par_help('Trackconfirmframes', subject='face')
		scriptOp.par.Trackconfirmframes = TRACKER_MIN_HITS
		p = page.appendFloat('Outputsmoothing', label='Output Smoothing', size=1)
		p[0].default = OUTPUT_SMOOTHING
		p[0].min = 0.0
		p[0].max = 1.0
		p[0].clampMin = True
		p[0].clampMax = True
		p[0].help = object_tracker.par_help('Outputsmoothing', extra=(
			"Keypoints/head direction have their OWN separate smoothing (Pose Smoothing below) -- "
			"they're held at their last real value across occlusion regardless, see class docstring. "
			"Kept lower than the other scripts' default since heavy smoothing reads as unnatural on a "
			"face's own head-turn motion."
		))
		scriptOp.par.Outputsmoothing = OUTPUT_SMOOTHING
		p = page.appendMenu('Posemethod', label='Head Pose Method', size=1)
		p[0].menuNames = ['geometric', 'solvepnp']
		p[0].menuLabels = ['Geometric (Keypoint Ratios)', 'SolvePnP (3D Model)']
		p[0].default = POSE_METHOD
		p[0].help = ("Which method estimates yaw/pitch/roll. Geometric: bounded distance ratios "
			"between the nose and the other 4 keypoints, no solver -- far less sensitive to keypoint "
			"noise, not a calibrated real angle (see Poseyawscale/Posepitchscale). SolvePnP: matches "
			"keypoints against a rough 3D face model via cv2.solvePnP -- a genuine 3D pose estimate, "
			"but sensitive to noise on only 5 sparse near-planar points (see Posefocalscale). Roll is "
			"identical either way -- it was never the problem, just the eye-line's 2D tilt angle.")
		scriptOp.par.Posemethod = POSE_METHOD
		p = page.appendFloat('Poseyawscale', label='Head Pose Yaw Scale (Geometric)', size=1)
		p[0].default = POSE_YAW_SCALE
		p[0].min = 1.0
		p[0].max = 1000.0
		p[0].clampMin = True
		p[0].clampMax = False
		p[0].help = ("Degrees-per-ratio scale for yaw specifically (only used when Head Pose Method "
			"= Geometric) -- kept separate from Head Pose Pitch Scale since yaw's underlying ratio "
			"covers a much smaller natural range than pitch's for the same real rotation. Tune live: "
			"if head turns look too subtle, increase; too exaggerated, decrease.")
		scriptOp.par.Poseyawscale = POSE_YAW_SCALE
		p = page.appendFloat('Posepitchscale', label='Head Pose Pitch Scale (Geometric)', size=1)
		p[0].default = POSE_PITCH_SCALE
		p[0].min = 1.0
		p[0].max = 1000.0
		p[0].clampMin = True
		p[0].clampMax = False
		p[0].help = ("Degrees-per-ratio scale for pitch specifically (only used when Head Pose Method "
			"= Geometric) -- see Head Pose Yaw Scale for why this is separate. Tune live: if head nods "
			"look too subtle, increase; too exaggerated, decrease.")
		scriptOp.par.Posepitchscale = POSE_PITCH_SCALE
		p = page.appendFloat('Posefocalscale', label='Head Pose Focal Scale (SolvePnP)', size=1)
		p[0].default = POSE_FOCAL_SCALE
		p[0].min = 0.1
		p[0].max = 5.0
		p[0].clampMin = True
		p[0].clampMax = False
		p[0].help = ("Multiplier on the assumed camera focal length (only used when Head Pose Method "
			"= SolvePnP) -- no real camera calibration available, so this is a stand-in you can "
			"calibrate live: if head-turn rotation looks too subtle for the real motion, increase; "
			"if it looks exaggerated, decrease. Does not affect box/keypoint detection at all, only "
			"the derived rotation angles.")
		scriptOp.par.Posefocalscale = POSE_FOCAL_SCALE
		p = page.appendFloat('Posesmoothing', label='Head Pose Smoothing', size=1)
		p[0].default = POSE_SMOOTHING
		p[0].min = 0.0
		p[0].max = 1.0
		p[0].clampMin = True
		p[0].clampMax = True
		p[0].help = ("Extra lerp on yaw/pitch/roll specifically (separate from Output Smoothing, "
			"which only smooths box position/size), applied regardless of Head Pose Method -- "
			"keypoint detection noise on just 5 sparse points can make raw per-frame angles look "
			"jittery even when not moving. 0 = raw/no smoothing, 1 = frozen in place.")
		scriptOp.par.Posesmoothing = POSE_SMOOTHING

	def get_model_path(self):
		"""Return path to the YuNet face detection model."""
		return os.path.join(project.folder, 'data', 'ml', 'yunet', 'face_detection_yunet_2023mar.onnx')

	def on_model_loaded(self, model):
		"""Called from the overridden _load_model_thread() below once cv2.FaceDetectorYN
		has been created successfully."""
		self.printONNX("YuNet face detector ready (cv2.FaceDetectorYN, OpenCV's DNN module -- not onnxruntime)")

	# ========== Overridden model loading / inference (see class docstring) ==========

	def _load_model_thread(self):
		"""Overrides ONNXInferenceManager._load_model_thread(): YuNet loads via OpenCV's
		cv2.FaceDetectorYN.create(), not ort.InferenceSession(), so this bypasses the
		base implementation entirely rather than trying to make it fit. self.session
		still ends up holding the loaded model object, and self.is_loading/load_error
		still get updated the same way -- everything else in the base class (onCook,
		get_loading_status()) keeps working unchanged."""
		self.is_loading = True
		self.load_error = None
		try:
			self.printONNX('=============================================')
			self.printONNX("Starting YuNet model loading in background...")
			model_path = self.get_model_path()
			self.printONNX("model:", model_path)

			# score_threshold here is YuNet's own internal, permissive pre-filter --
			# Confthreshold below does the real, user-tunable filtering downstream in
			# postprocess(). nms_threshold is this detector's only NMS pass (not
			# duplicated downstream -- see the no-separate-NMS-pass comment there).
			temp_model = cv2.FaceDetectorYN.create(
				model_path,
				"",            # config path (unused for this export)
				(256, 256),    # placeholder input size -- actual size set per-frame in preprocess()
				0.5,           # internal score threshold
				0.3,           # internal NMS threshold
				5000,          # top_k
			)

			self.on_model_loaded(temp_model)
			self.session = temp_model
			self.printONNX("YuNet model loaded successfully!")
			self.printONNX('=============================================')
		except Exception as e:
			self.load_error = str(e)
			self.printONNX(f"Error loading YuNet model: {e}")
		finally:
			self.is_loading = False

	def run_inference(self, input_tensor):
		"""Overrides ONNXInferenceManager.run_inference(): calls cv2.FaceDetectorYN.detect()
		instead of an onnxruntime session.run() -- self.session here is a cv2.FaceDetectorYN
		object, not an ort.InferenceSession, so it has no .run() method at all. This is the
		correct override point (base class's _worker_loop() wraps it with timing/locking/
		exception-handling); see Round 2 in td-threaded-inference-optimization.md for a
		past bug where this script overrode a stale worker-method name instead."""
		_, faces = self.session.detect(input_tensor)
		return faces

	def preprocess(self, nA):
		"""Preprocess input for YuNet: a plain BGR uint8 image (cv2.FaceDetectorYN.detect()
		expects this, not a normalized float tensor). Also keeps YuNet's own input size in
		sync with the actual frame dimensions -- unlike the fixed-640 YOLO models, YuNet is
		a variable-input-resolution architecture and needs setInputSize() called whenever
		that changes."""
		self.original_h, self.original_w = nA.shape[:2]
		num_channels = nA.shape[2] if len(nA.shape) == 3 else 1

		if num_channels >= 3:
			# flip V + RGB(A)->BGR (drop alpha) + denormalize to uint8, in one view+cast
			img_bgr = np.ascontiguousarray((nA[::-1, :, 2::-1] * 255).astype(np.uint8))
		else:
			gray = (self.npu.flip_v(nA) * 255).astype(np.uint8)
			img_bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

		current_size = (self.original_w, self.original_h)
		if self._cached_input_size != current_size:
			self.session.setInputSize(current_size)
			self._cached_input_size = current_size
			self.printONNX(f"Set YuNet input size to: {current_size}")

		return img_bgr

	def postprocess(self, outputs):
		"""Postprocess YuNet's detection output (an (N, 15) array: x,y,w,h (pixel space),
		5 keypoints x,y (pixel space), score -- or None if no faces at all)."""
		faces = outputs

		# Read thresholds from custom parameters (updated each frame)
		self.conf_threshold = self._par_or_default('Confthreshold', CONF_THRESHOLD)
		self.low_conf_threshold = self._par_or_default('Lowconfthreshold', LOW_CONF_THRESHOLD)
		min_box_width = self._par_or_default('Minboxwidth', MIN_BOX_WIDTH)
		min_box_height = self._par_or_default('Minboxheight', MIN_BOX_HEIGHT)
		self.tracker.high_thresh = self.conf_threshold
		self.tracker.low_thresh = self.low_conf_threshold
		self.tracker.match_thresh = self._par_or_default('Trackiouthreshold', TRACKER_IOU_THRESHOLD)
		self.tracker.track_buffer = self._par_or_default('Tracklossframes', TRACKER_MAX_AGE)
		self.tracker.min_hits = int(self._par_or_default('Trackconfirmframes', TRACKER_MIN_HITS))
		smoothing = self._par_or_default('Outputsmoothing', OUTPUT_SMOOTHING)
		pose_method = self._par_or_default('Posemethod', POSE_METHOD)
		yaw_scale = self._par_or_default('Poseyawscale', POSE_YAW_SCALE)
		pitch_scale = self._par_or_default('Posepitchscale', POSE_PITCH_SCALE)
		focal_scale = self._par_or_default('Posefocalscale', POSE_FOCAL_SCALE)
		pose_smoothing = self._par_or_default('Posesmoothing', POSE_SMOOTHING)

		detections = []
		if faces is not None and len(faces) > 0:
			x, y, w, h = faces[:, 0], faces[:, 1], faces[:, 2], faces[:, 3]
			scores = faces[:, 14]

			boxes_xyxy = np.stack([x, x + w, y, y + h], axis=1)[:, [0, 2, 1, 3]].astype(np.float32)
			boxes_xyxy /= np.array([self.original_w, self.original_h, self.original_w, self.original_h], dtype=np.float32)

			kps = faces[:, 4:4 + NUM_KEYPOINTS * 2].reshape(-1, NUM_KEYPOINTS, 2).astype(np.float32)
			kps /= np.array([self.original_w, self.original_h], dtype=np.float32)

			# Keep everything down to the LOW threshold -- ByteTracker does its own
			# high/low split internally for the two-stage association, so pre-filtering
			# to the high threshold here would defeat the low-confidence recovery pass.
			valid = scores > self.low_conf_threshold
			valid &= (boxes_xyxy[:, 2] - boxes_xyxy[:, 0] >= min_box_width) & (boxes_xyxy[:, 3] - boxes_xyxy[:, 1] >= min_box_height)

			boxes_xyxy = boxes_xyxy[valid]
			scores = scores[valid]
			kps = kps[valid]

			# Clip boxes to [0, 1]
			boxes_xyxy = np.clip(boxes_xyxy, 0.0, 1.0)

			# Flip Y-axis for TouchDesigner (model uses top-down, TD uses bottom-up)
			boxes_xyxy[:, 1], boxes_xyxy[:, 3] = 1.0 - boxes_xyxy[:, 3], 1.0 - boxes_xyxy[:, 1]
			kps[:, :, 1] = 1.0 - kps[:, :, 1]

			# No separate NMS pass here -- unlike the ONNX-runtime-based scripts in this
			# project, YuNet's own cv2.FaceDetectorYN already runs an internal NMS at
			# creation time (see _load_model_thread()), so a second pass here would just
			# be redundant complexity/a confusing second (non-tunable-together) knob.
			for i in range(len(boxes_xyxy)):
				detections.append({
					'box': boxes_xyxy[i].tolist(),
					'score': float(scores[i]),
					'keypoints': kps[i].tolist(),  # 5 x [x, y], TD coords
				})

		# Update tracker (runs on main thread, no lock needed)
		active_tracks = self.tracker.update(detections)

		# Build structured data for CHOP/table output (filter out decayed/unconfirmed tracks)
		active_ids = {t.track_id for t in active_tracks}

		# Isotropic box-size correction -- see docs/learnings/debug-comp-camera-aspect.md's
		# "Bug 3". YuNet's box regression, like BlazeFace/SCRFD's, comes out of the
		# anisotropically-squished square input (fit_square_sm's 'fill' mode) roughly
		# isotropic. Naively reprojecting its square-space w/h fractions independently
		# against true_w/true_h produces a box whose aspect drifts toward the true frame's
		# own aspect instead of the real face's shape (worst under a severe, e.g. portrait,
		# input aspect). Re-expressing the size as a fraction of each axis's own true
		# dimension, rather than reprojecting independently, fixes this the same way it
		# was fixed for the mediapipe/hands landmark detectors.
		null_passthrough = self.scriptOp.parent().op('null_passthrough')
		true_w = null_passthrough.width if null_passthrough is not None else self.original_w
		true_h = null_passthrough.height if null_passthrough is not None else self.original_h
		true_aspect = true_w / true_h

		self.tracked_objects = []
		for t in active_tracks:
			# t.confirmed gates display, same reasoning as the score check just below --
			# a track still in its min_hits confirmation window is genuinely "alive"
			# (kept in active_ids, keeps its tracker-side Kalman/box/keypoint state) but
			# not yet trusted as a real face, exactly like a track kept alive only by
			# low-confidence recovery.
			if t.score < self.conf_threshold or not t.confirmed:
				continue
			box = t.box  # Kalman estimate
			smoothed = object_tracker.box_smooth(self._box_state, t.track_id, box, smoothing)

			# Keypoints/head direction: only advance on a frame where this track
			# actually matched a real detection -- a Kalman-predicted-only frame
			# (lost_frames > 0) has no new keypoint data at all. Held state persists
			# across occlusion instead of resetting, same reasoning as
			# onnx_yolo26_pose.py's _kpt_state.
			raw_kpts = t.payload.get('keypoints')
			if t.lost_frames == 0 and raw_kpts is not None:
				# Keypoints are positions, same as the box -- smoothed with the same
				# Outputsmoothing lerp rather than left raw, so facial markers don't
				# jitter independently of the (already-smoothed) box they sit inside.
				# Smoothing happens BEFORE head-direction is derived from them, so it's
				# a genuine noise reduction on the pose input, not just cosmetic on
				# top -- complements (doesn't duplicate) Posesmoothing's separate lerp
				# on the resulting yaw/pitch/roll output below.
				prev_pose = self._kpt_state.get(t.track_id)
				if prev_pose is not None and prev_pose.get('keypoints') is not None:
					prev_kpts = prev_pose['keypoints']
					smoothed_kpts = [
						[prev_kpts[k][0] * smoothing + raw_kpts[k][0] * (1.0 - smoothing),
						 prev_kpts[k][1] * smoothing + raw_kpts[k][1] * (1.0 - smoothing)]
						for k in range(NUM_KEYPOINTS)
					]
				else:
					smoothed_kpts = [list(kp) for kp in raw_kpts]

				if pose_method == 'solvepnp':
					yaw, pitch, roll = _compute_head_direction_solvepnp(smoothed_kpts, self.original_w, self.original_h, focal_scale)
				else:
					yaw, pitch, roll = _compute_head_direction_geometric(smoothed_kpts, yaw_scale, pitch_scale)
				if prev_pose is not None:
					yaw = prev_pose['yaw'] * pose_smoothing + yaw * (1.0 - pose_smoothing)
					pitch = prev_pose['pitch'] * pose_smoothing + pitch * (1.0 - pose_smoothing)
					roll = prev_pose['roll'] * pose_smoothing + roll * (1.0 - pose_smoothing)
				self._kpt_state[t.track_id] = {'keypoints': smoothed_kpts, 'yaw': yaw, 'pitch': pitch, 'roll': roll}
			state = self._kpt_state.get(t.track_id, {'keypoints': [[0.0, 0.0]] * NUM_KEYPOINTS, 'yaw': 0.0, 'pitch': 0.0, 'roll': 0.0})

			cx = (smoothed[0] + smoothed[2]) / 2
			cy = (smoothed[1] + smoothed[3]) / 2
			w_ = (smoothed[2] - smoothed[0]) / math.sqrt(true_aspect)
			h_ = (smoothed[3] - smoothed[1]) * math.sqrt(true_aspect)
			self.tracked_objects.append({
				'track_id': t.track_id,
				'score': t.score,
				'cx': cx, 'cy': cy, 'w': w_, 'h': h_,
				'x_left': smoothed[0],
				'x_right': smoothed[2],
				'y_top': smoothed[3],     # top edge of bbox (TD coords)
				'y_bottom': smoothed[1],  # bottom edge of bbox (TD coords)
				'vx': float(t.mean[4]), 'vy': float(t.mean[5]),  # Kalman-estimated box-center velocity
				'lost_frames': t.lost_frames,
				'total_frames': t.total_frames,
				'keypoints': state['keypoints'],
				'yaw': state['yaw'], 'pitch': state['pitch'], 'roll': state['roll'],
			})

		# Prune box/keypoint state for tracks the tracker has dropped entirely.
		object_tracker.prune_stale(active_ids, self._box_state, self._kpt_state)

		# Draw output image
		if DRAW_BOXES:
			output_img = self.npu.flip_v(self.draw_tracked_faces())
		else:
			# Black frame — no need to zero or flip each frame, just reuse static buffer
			needed_shape = (self.original_h, self.original_w, 3)
			if self._output_buf is None or self._output_buf_shape != needed_shape:
				self._output_buf = np.zeros(needed_shape, dtype=np.float32)
				self._output_buf_shape = needed_shape
			output_img = self._output_buf

		return output_img

	def on_result_published(self):
		"""Flush table_output/table_joints from tracked_objects right after this frame's
		texture publishes, before the next frame's capture/dispatch -- see
		ONNXInferenceManager.on_result_published()'s docstring."""
		self.write_tracks_to_table()
		self.write_joints_to_table()

	def draw_tracked_faces(self):
		"""Render bounding boxes + keypoints for tracked faces onto a blank image.
		Returns an RGB float32 (0-1) image at original resolution."""
		output_img = np.zeros((self.original_h, self.original_w, 3), dtype=np.float32)

		if not self.tracked_objects:
			return output_img

		draw_img = np.zeros((self.original_h, self.original_w, 3), dtype=np.uint8)
		w, h = self.original_w, self.original_h

		def to_px(td_x, td_y):
			"""TD-normalized coords (y: 0=bottom, 1=top) -> pixel (col, row) in this
			function's plain top-down array (row 0 = top); flipped back to TD's
			bottom-up convention afterward (see postprocess())."""
			return object_tracker.td_to_px(td_x, td_y, w, h)

		for obj in self.tracked_objects:
			if obj['lost_frames'] > 0 and obj['score'] < self.conf_threshold * 0.5:
				continue  # Skip faded-out unmatched tracks

			px1, py_bottom = to_px(obj['x_left'], obj['y_bottom'])
			px2, py_top = to_px(obj['x_right'], obj['y_top'])

			color = BOX_COLOR_BGR
			if obj['lost_frames'] > 0:
				fade = object_tracker.track_fade(obj['lost_frames'], self.tracker.track_buffer)
				color = tuple(int(c * fade) for c in color)

			cv2.rectangle(draw_img, (px1, py_top), (px2, py_bottom), color, 2)

			for kx, ky in obj['keypoints']:
				kpx, kpy = to_px(kx, ky)
				cv2.circle(draw_img, (kpx, kpy), 2, KEYPOINT_COLOR_BGR, -1)

			label = f"#{obj['track_id']} {obj['score']:.0%} yaw={obj['yaw']:+.0f}deg"
			font_scale = 0.5
			(tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
			cv2.rectangle(draw_img, (px1, py_top - th - 6), (px1 + tw + 4, py_top), color, -1)
			cv2.putText(draw_img, label, (px1 + 2, py_top - 4),
				cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 0), 1, cv2.LINE_AA)

		# Convert BGR uint8 -> RGB float32 (0-1)
		return cv2.cvtColor(draw_img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0

	# ==================== CHOP TRACKING OUTPUT ====================
	# To output tracking data to a CHOP, use a Script CHOP DAT with:
	#
	#   mgr = op('script1').module.inference_manager
	#   tracks = mgr.tracked_objects  # list of dicts
	#
	# Each dict contains: track_id, score, cx, cy, w, h, x_left, x_right, y_top,
	#   y_bottom, vx, vy (Kalman-estimated), lost_frames, total_frames,
	#   keypoints (5 x [x, y]), yaw, pitch, roll
	#
	# For a Table DAT approach, call write_tracks_to_table() from a
	# Script DAT or Execute DAT each frame.

	def write_tracks_to_table(self):
		"""Helper to write current tracking data to a Table DAT. Column order matches
		onnx_yolo26_obj_det.py's core columns exactly (minus class_id/class_name -- a
		face detector has no classes), with face-specific extras (yaw/pitch/roll/
		keypoints) appended -- so table_output's existing consumers (Debug's geo/select
		nodes, which read by column NAME) need no changes."""
		tbl = self.opOutputTableDAT
		if tbl is None:
			return

		kpt_header = []
		for name in KEYPOINT_NAMES:
			kpt_header += [f'{name}_x', f'{name}_y']

		tbl.clear()
		# yaw/pitch/roll are all in DEGREES, but exactly how "real" depends on Posemethod
		# -- see _compute_head_direction_geometric()/_compute_head_direction_solvepnp()'s
		# docstrings. yaw = left/right turn, pitch = nod, roll = tilt (a genuine angle
		# either way).
		tbl.appendRow([
			*object_tracker.label_header(),
			*object_tracker.box_header(),
			'yaw', 'pitch', 'roll',
			*kpt_header,
			*object_tracker.color_header(),
		])
		for obj in self.tracked_objects:
			flat_kpts = [v for kp in obj['keypoints'] for v in kp]  # 5*2 flat list
			tbl.appendRow([
				*object_tracker.label_row(obj['track_id'], obj['score']),
				*object_tracker.box_row(obj),
				f"{obj['yaw']:.4f}", f"{obj['pitch']:.4f}", f"{obj['roll']:.4f}",
				*[f"{v:.4f}" for v in flat_kpts],
				*object_tracker.color_row(obj['track_id']),
			])

	def write_joints_to_table(self):
		"""Flat per-keypoint Table DAT, one row per keypoint across ALL tracked faces --
		shared table_joints schema, see object_tracker.joints_header()'s docstring. YuNet's
		5 keypoints are 2D-only (no z) and have no per-point confidence, so both are
		constant stand-ins (0.0 / 1.0). No table_bones -- these 5 points (eyes/nose/mouth)
		don't form a natural skeleton the way pose/hand joints do."""
		tbl = self.opJointsTableDAT
		if tbl is None:
			return
		tbl.clear()
		tbl.appendRow(object_tracker.joints_header())
		for obj in self.tracked_objects:
			track_id = obj['track_id']
			for name, (kx, ky) in zip(KEYPOINT_NAMES, obj['keypoints']):
				tbl.appendRow(object_tracker.joints_row(track_id, name, kx, ky, 0.0, 1.0))


# Create global instance -- shut down any PREVIOUS instance first (releases its
# GPU-resident ONNX Runtime session(s) and stops its worker thread) so a script
# reload during active development doesn't leak both -- see
# onnx_inference_manager.shutdown_and_register()'s docstring for the full
# mechanism this avoids (and why it's NOT TD's own store()/fetch(), which risked
# a real crash trying to persist a live, unpicklable manager instance).
inference_manager = YuNetInference()
onnx_inference_manager.shutdown_and_register(parent().path, inference_manager)

# TouchDesigner callback wrappers that delegate to the manager
def onSetupParameters(scriptOp):
	return inference_manager.onSetupParameters(scriptOp)


def onPulse(par):
	return inference_manager.onPulse(par)


def onCook(scriptOp):
	# Run base manager cook (handles model loading, inference dispatch, copyNumpyArray).
	# Table writes happen inside this call now, via on_result_published().
	inference_manager.onCook(scriptOp)

	# Optionally draw boxes/keypoints on main thread (if enabled)
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

	AUTOMATIC alone can't drive this pipeline reliably: anything reading
	tracked_objects via a raw Python module reference (not a wire/parameter) is
	invisible to TD's "is the output being used" dependency check, so AUTOMATIC can
	stop cooking this even while something downstream still depends on it.

	Unconditionally ALWAYS rather than switching to AUTOMATIC while paused: CookLevel is
	only reconsidered when TD decides whether to attempt a cook at all, so once AUTOMATIC
	settles into "not cooking" nothing prompts it to re-check later -- resuming play isn't
	a registered dependency of this op, so it never recovers on its own. The play/pause
	skip instead lives in ONNXInferenceManager.onCook() itself (checks
	scriptOp.time.play and returns early), which keeps this op always eligible to cook
	every frame so the very next real cook after resuming naturally picks back up.
	"""

	return CookLevel.ALWAYS
