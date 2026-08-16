import os
import numpy as np
import cv2

# custom util imports
import numpy as npu
import onnx_inference_manager
import object_tracker

# Import the base inference manager
ONNXInferenceManager = onnx_inference_manager.ONNXInferenceManager
ByteTracker = object_tracker.ByteTracker
_nms = object_tracker.nms
_track_color = object_tracker.track_color

# COCO class names (80 classes, used by YOLO26)
COCO_CLASSES = {
	0: 'person', 1: 'bicycle', 2: 'car', 3: 'motorcycle', 4: 'airplane',
	5: 'bus', 6: 'train', 7: 'truck', 8: 'boat', 9: 'traffic light',
	10: 'fire hydrant', 11: 'stop sign', 12: 'parking meter', 13: 'bench', 14: 'bird',
	15: 'cat', 16: 'dog', 17: 'horse', 18: 'sheep', 19: 'cow',
	20: 'elephant', 21: 'bear', 22: 'zebra', 23: 'giraffe', 24: 'backpack',
	25: 'umbrella', 26: 'handbag', 27: 'tie', 28: 'suitcase', 29: 'frisbee',
	30: 'skis', 31: 'snowboard', 32: 'sports ball', 33: 'kite', 34: 'baseball bat',
	35: 'baseball glove', 36: 'skateboard', 37: 'surfboard', 38: 'tennis racket', 39: 'bottle',
	40: 'wine glass', 41: 'cup', 42: 'fork', 43: 'knife', 44: 'spoon',
	45: 'bowl', 46: 'banana', 47: 'apple', 48: 'sandwich', 49: 'orange',
	50: 'broccoli', 51: 'carrot', 52: 'hot dog', 53: 'pizza', 54: 'donut',
	55: 'cake', 56: 'chair', 57: 'couch', 58: 'potted plant', 59: 'bed',
	60: 'dining table', 61: 'toilet', 62: 'tv', 63: 'laptop', 64: 'mouse',
	65: 'remote', 66: 'keyboard', 67: 'cell phone', 68: 'microwave', 69: 'oven',
	70: 'toaster', 71: 'sink', 72: 'refrigerator', 73: 'book', 74: 'clock',
	75: 'vase', 76: 'scissors', 77: 'teddy bear', 78: 'hair drier', 79: 'toothbrush'
}

# ==================== CONFIGURATION ====================
# This runner is dedicated to PEOPLE segmentation specifically (not a general 80-class
# tool like onnx_yolo26_obj_det.py) -- restricting to one class keeps ByteTracker's
# class-agnostic (pure IoU) matching safe (see onnx_yolo26_obj_det.py's identical
# CLASSES_TO_DETECT comment for why that stops being true with multiple classes) and
# lets mask coloring below key off track_id alone rather than juggling per-class color
# assignment for classes we'll never actually see.
CLASSES_TO_DETECT = ['person']

# Which model variant to use: 'yolo26n-seg' (faster) or 'yolo26s-seg' (more accurate).
# Both are Ultralytics end2end exports, same convention as onnx_yolo26_pose.py's model:
#   output0 [1, 300, 38] -- 300 pre-sorted/filtered candidates, 38 = 4 box + 1 conf +
#            1 class_id + 32 mask coefficients
#   output1 [1, 32, 160, 160] -- mask prototypes
# UNLIKE the pose model, this export's box coordinates are pixel-space (0-640ish), not
# normalized 0-1 -- postprocess() auto-detects and normalizes either way (box_max check)
# so this isn't hardcoded as an assumption that could silently go stale.
MODEL_VARIANT = 'yolo26s-seg'

# Confidence threshold for a detected person to be shown/tracked (0.0 - 1.0). This is
# ByteTracker's "high confidence" threshold -- detections at or above this score are
# matched first and can start brand-new tracks.
CONF_THRESHOLD = 0.35

# ByteTracker's "low confidence" threshold. Detections scoring between this and
# CONF_THRESHOLD are never used to start a new track, but ARE used in a second
# association pass to recover existing tracks that a plain confidence-thresholded
# detector would otherwise drop (occlusion, motion blur, partial visibility) -- this is
# ByteTrack's actual innovation. Detections below this are discarded as background.
LOW_CONF_THRESHOLD = 0.1

# IoU threshold for NMS applied to raw per-frame detections before tracking (lower =
# more aggressive suppression). See object_tracker.nms().
NMS_IOU_THRESHOLD = 0.5

# Minimum box width/height (normalized 0-1, fraction of frame dimension) for a detection
# to be kept at all -- applied alongside Confthreshold, before NMS/tracking. Separate
# width/height floors, NOT one shared value applied to both axes -- see the identical
# comment in onnx_yolo26_pose.py/onnx_yolo26_obj_det.py for why a single shared threshold
# ends up rejecting real, legitimately-tall-but-narrow people once tuned high enough to
# reject noise.
MIN_BOX_WIDTH = 0.02
MIN_BOX_HEIGHT = 0.02

# Reject decoded masks that fill less than this fraction of THEIR OWN detection box
# (after cropping the mask to that box -- see the crop comment in postprocess()), not a
# fraction of the whole frame -- scale-invariant regardless of how near/far a person is,
# where a fixed frame-fraction floor would unfairly reject a distant person whose box is
# naturally tiny in absolute pixels even though their mask fills it perfectly well. A real
# person's silhouette typically fills something like 35-70% of their own box (limb gaps
# keep it well under 100%); much lower usually means a degenerate/noisy mask. Checked
# AFTER NMS -- mask decode (coefficients x prototypes matmul) is the single most
# expensive step here, so only ever run it on survivors, never on the full raw candidate pool.
MIN_MASK_AREA_RATIO = 0.15

# Sigmoid probability cutoff used ONLY to compute the fill-ratio noise-rejection check
# (MIN_MASK_AREA_RATIO) -- does NOT binarize the visual output, which stays soft/
# continuous all the way through (see class docstring). Higher = stricter about what
# counts as "filled" for that noise check.
MASK_THRESHOLD = 0.5

# Whether to write per-frame tracking data to table_output at all. This is pure "data
# output" overhead, separate from the visual matte -- iterating every confirmed track,
# formatting ~17 columns each, and clear()/appendRow()-ing a Table DAT every frame, which
# also cascades into whatever else is wired to table_output (e.g. Debug's geo_boxes).
# Off by default is NOT assumed here (default True, matching every other script in this
# project) -- flip Outputtrackdata off only when nothing actually reads table_output and
# the matte image is the only thing this script needs to produce.
OUTPUT_TRACK_DATA = True

# Tracker: max frames to keep a lost track alive.
TRACKER_MAX_AGE = 30

# Tracker: min IoU to accept a match between a track and a detection.
TRACKER_IOU_THRESHOLD = 0.3

# Tracker: total matched frames (not necessarily consecutive -- see object_tracker.Track's
# confirmed/hits) a brand-new track needs before it's confirmed and shown/output at all.
# Cuts down on both overlap with existing boxes and single-frame noise "detections"
# registering as a real person -- almost none of that noise ever gets a second real match
# at all before track_buffer prunes it.
TRACKER_MIN_HITS = 3

# Smoothing factor for box position/size lerp (0 = no smoothing, 1 = frozen). Applies
# only to the box -- masks are NOT smoothed pixel-wise (no optical flow here); a track's
# mask is simply held at its last real decoded value across lost/predicted-only frames
# rather than blended or re-decoded from stale coefficients (see _mask_state).
OUTPUT_SMOOTHING = 0.5

# Draw masks/boxes on the output image?
DRAW_BOXES = False



# ==================== YOLO26 PEOPLE SEGMENTATION ====================

class YOLO26SegmentationInference(ONNXInferenceManager):
	"""YOLO26 instance segmentation, specialized for tracked PEOPLE segmentation.

	Targets the Ultralytics end2end (one-to-one trained) ONNX export: output0
	(1, 300, 38) pre-sorted by confidence, output1 (1, 32, 160, 160) mask prototypes --
	same family/convention as onnx_yolo26_pose.py's model (see MODEL_VARIANT comment for
	the box-coordinate-space difference from pose).

	Tracking uses `object_tracker.ByteTracker` (shared across every ONNX script in this
	project) for the full box-tracking lifecycle -- Kalman motion prediction, optimal
	(Hungarian) assignment, and ByteTrack's two-stage high/low-confidence association.
	Box position/size is smoothed on top of the tracker's own Kalman estimate
	(self._box_state), the same role Outputsmoothing plays in onnx_yolo26_obj_det.py.
	Masks are handled separately (self._mask_state) since a segmentation mask has no
	sensible "velocity" to Kalman-predict or lerp pixel-by-pixel -- a track just holds
	its last real decoded mask across any frame it isn't freshly re-detected.

	The matte is output at the mask prototype's NATIVE resolution (160x160 for this
	model family), not upscaled to the input's 640x640 -- upscaling an already-binary
	silhouette in Python can't recover boundary detail the 160x160 grid never captured
	(it just blows up the same blocky edges), and doing it in Python costs real CPU every
	frame for no visual benefit. Scaling up (and any feathering) belongs downstream in
	TD's own GPU pipeline (a Resolution/Transform TOP, optionally a Blur TOP), which is
	both faster and gives full control over the upscale/feather method. The composite
	itself stays as soft (pre-threshold) sigmoid probabilities rather than a hard binary
	mask specifically so that downstream upscale has continuous values to interpolate --
	a hard binary field upscaled later still looks jagged, a soft field upscales into a
	naturally anti-aliased edge. Maskthreshold still exists, but only gates which
	detections get accepted/tracked at all (noise rejection), not what the visual output
	looks like.
	"""

	def __init__(self):
		super().__init__()
		self.opOutputTableDAT = parent().op('table_output')  # Optional Table DAT for structured output
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
		# Per-track LAST KNOWN decoded mask (proto-resolution soft float32 probability
		# array, box-cropped but NOT hard-thresholded -- see postprocess()), keyed by
		# track_id -- held across lost/predicted-only frames rather than smoothed or
		# re-decoded (see class docstring).
		self._mask_state = {}
		# Mask prototype resolution -- output resolution of this script's matte image.
		# Set from the model's actual output shape on first real inference; the 160x160
		# default matches this model family's confirmed architecture (see MODEL_VARIANT
		# comment) and is only ever used before that first frame lands.
		self._proto_h = 160
		self._proto_w = 160
		# Structured tracking data exposed for CHOP/table consumption
		self.tracked_objects = []
		# Pre-allocated buffers (lazily sized)
		self._output_buf = None
		self._output_buf_shape = None
		self._input_tensor_buf = None   # pre-allocated NCHW input buffer
		self._input_buf_shape = None
		# Cache target class IDs
		self._target_ids_array = np.array(
			[idx for idx, name in COCO_CLASSES.items() if name in CLASSES_TO_DETECT],
			dtype=np.intp
		) if CLASSES_TO_DETECT else None

	def onSetupParameters(self, scriptOp):
		"""Add YOLO26-Seg-specific parameters alongside base class params."""
		super().onSetupParameters(scriptOp)
		page = scriptOp.appendCustomPage('YOLO26-Seg')
		p = page.appendFloat('Confthreshold', label='Confidence Threshold', size=1)
		p[0].default = CONF_THRESHOLD
		p[0].min = 0.0
		p[0].max = 1.0
		p[0].clampMin = True
		p[0].clampMax = True
		p[0].help = object_tracker.par_help('Confthreshold')
		scriptOp.par.Confthreshold = CONF_THRESHOLD
		p = page.appendFloat('Lowconfthreshold', label='Low Confidence Threshold (Recovery)', size=1)
		p[0].default = LOW_CONF_THRESHOLD
		p[0].min = 0.0
		p[0].max = 1.0
		p[0].clampMin = True
		p[0].clampMax = True
		p[0].help = object_tracker.par_help('Lowconfthreshold')
		scriptOp.par.Lowconfthreshold = LOW_CONF_THRESHOLD
		p = page.appendFloat('Nmsiouthreshold', label='NMS IoU Threshold (Dedup)', size=1)
		p[0].default = NMS_IOU_THRESHOLD
		p[0].min = 0.0
		p[0].max = 1.0
		p[0].clampMin = True
		p[0].clampMax = True
		p[0].help = object_tracker.par_help('Nmsiouthreshold', subject='person', subject_plural='people')
		scriptOp.par.Nmsiouthreshold = NMS_IOU_THRESHOLD
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
		p = page.appendFloat('Minmaskarea', label='Min Mask Fill Ratio (Of Own Box)', size=1)
		p[0].default = MIN_MASK_AREA_RATIO
		p[0].min = 0.0
		p[0].max = 1.0
		p[0].clampMin = True
		p[0].clampMax = True
		p[0].help = ("Rejects a decoded mask if it fills less than this fraction of ITS OWN detection "
			"box (not a fraction of the whole frame -- scale-invariant regardless of how near/far a "
			"person is). A real silhouette typically fills ~35-70% of its own box (limb gaps keep it "
			"under 100%); much lower usually means a degenerate/noisy mask.")
		scriptOp.par.Minmaskarea = MIN_MASK_AREA_RATIO
		p = page.appendFloat('Maskthreshold', label='Mask Threshold (Noise Filter Only)', size=1)
		p[0].default = MASK_THRESHOLD
		p[0].min = 0.0
		p[0].max = 1.0
		p[0].clampMin = True
		p[0].clampMax = True
		p[0].help = ("Sigmoid cutoff used ONLY to compute Min Mask Fill Ratio's noise check -- does NOT "
			"binarize the visual matte, which stays soft/continuous the whole way through so it upscales "
			"cleanly downstream in TD. Higher = stricter about what counts as \"filled\" for that check.")
		scriptOp.par.Maskthreshold = MASK_THRESHOLD
		p = page.appendToggle('Outputtrackdata', label='Output Track Data (Table)')
		p[0].default = OUTPUT_TRACK_DATA
		p[0].help = ("Whether to write per-frame tracking data to table_output at all. Pure performance "
			"toggle: this is real per-frame CPU work (formatting every column for every confirmed "
			"track) that's entirely separate from the visual matte -- turn off if nothing downstream "
			"actually reads table_output.")
		scriptOp.par.Outputtrackdata = OUTPUT_TRACK_DATA
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
		p[0].help = object_tracker.par_help('Trackiouthreshold', subject='person')
		scriptOp.par.Trackiouthreshold = TRACKER_IOU_THRESHOLD
		p = page.appendFloat('Trackconfirmframes', label='Track Confirm Frames', size=1)
		p[0].default = TRACKER_MIN_HITS
		p[0].min = 1.0
		p[0].max = 30.0
		p[0].clampMin = True
		p[0].clampMax = False
		p[0].help = object_tracker.par_help('Trackconfirmframes', subject='person')
		scriptOp.par.Trackconfirmframes = TRACKER_MIN_HITS
		p = page.appendFloat('Outputsmoothing', label='Output Smoothing (Box)', size=1)
		p[0].default = OUTPUT_SMOOTHING
		p[0].min = 0.0
		p[0].max = 1.0
		p[0].clampMin = True
		p[0].clampMax = True
		p[0].help = object_tracker.par_help('Outputsmoothing', extra=(
			"Masks themselves are NOT smoothed by this -- see class docstring."
		))
		scriptOp.par.Outputsmoothing = OUTPUT_SMOOTHING

	def get_model_path(self):
		"""Return path to YOLO26 segmentation model (see MODEL_VARIANT comment for the
		confirmed export format)."""
		model_dir = os.path.join(project.folder, 'data', 'ml', 'yolo26')
		return os.path.join(model_dir, f'{MODEL_VARIANT}.onnx')

	def on_model_loaded(self, session):
		"""Log model I/O and warn if the export doesn't match the confirmed format."""
		outputs = session.get_outputs()
		self.printONNX(f"YOLO26-Seg model outputs ({len(outputs)}):")
		for i, o in enumerate(outputs):
			self.printONNX(f"  [{i}] name='{o.name}' shape={o.shape} type={o.type}")
		inputs = session.get_inputs()
		for i, inp in enumerate(inputs):
			self.printONNX(f"  input[{i}] name='{inp.name}' shape={inp.shape} type={inp.type}")
		self.check_providers(session)
		if len(outputs) != 2:
			self.printONNX(
				f"WARNING: expected 2 outputs (detections + mask protos), got {len(outputs)} -- "
				"postprocess() assumes the Ultralytics end2end seg export format "
				"(see MODEL_VARIANT comment)."
			)

	def preprocess(self, nA):
		"""Preprocess input for YOLO26-Seg model. Assumes TD has already resized input to
		the model's expected dimensions (e.g. 640x640) upstream (this network's
		fit_square_sm), same assumption onnx_yolo26_pose.py/onnx_yolo26_obj_det.py make --
		no redundant internal cv2.resize."""
		self.original_h, self.original_w = nA.shape[:2]
		num_channels = nA.shape[2] if len(nA.shape) == 3 else 1

		if num_channels >= 3:
			needed = (1, 3, self.original_h, self.original_w)
			if self._input_buf_shape != needed:
				self._input_tensor_buf = np.empty(needed, dtype=np.float32)
				self._input_buf_shape = needed
			flipped = nA[::-1, :, :3]  # flip V + drop alpha (view, no alloc)
			self._input_tensor_buf[0, 0] = flipped[:, :, 0]
			self._input_tensor_buf[0, 1] = flipped[:, :, 1]
			self._input_tensor_buf[0, 2] = flipped[:, :, 2]
		else:
			img = self.npu.flip_v(nA)
			img = self.npu.grayscale_to_rgb(img)
			self._input_tensor_buf = np.ascontiguousarray(img.transpose(2, 0, 1)[np.newaxis], dtype=np.float32)
			self._input_buf_shape = self._input_tensor_buf.shape

		return self._input_tensor_buf

	def postprocess(self, outputs):
		"""Postprocess YOLO26-Seg outputs: end2end format, already NMS'd by the graph.

		output0 columns: [0:4]=box (pixel-space, auto-normalized below), [4]=conf,
		[5]=class_id, [6:38]=32 mask coefficients. output1 = mask prototypes.
		"""
		if len(outputs) != 2:
			needed_shape = (self._proto_h, self._proto_w, 3)
			if self._output_buf is None or self._output_buf_shape != needed_shape:
				self._output_buf = np.zeros(needed_shape, dtype=np.float32)
				self._output_buf_shape = needed_shape
			return self.npu.flip_v(self._output_buf)

		pred = outputs[0][0]          # (300, 38)
		mask_protos = outputs[1][0]   # (32, proto_h, proto_w)
		self._proto_h, self._proto_w = mask_protos.shape[1], mask_protos.shape[2]
		num_mask_coeffs = mask_protos.shape[0]
		proto_h, proto_w = mask_protos.shape[1], mask_protos.shape[2]

		boxes_raw = pred[:, 0:4].copy()
		confidences = pred[:, 4].copy()
		class_ids = pred[:, 5].astype(np.intp)
		mask_coeffs = pred[:, 6:6 + num_mask_coeffs].copy()

		# Auto-detect pixel-space vs normalized boxes -- this export's boxes run in
		# pixel-space (0-640ish), unlike the pose model's normalized 0-1, but checking
		# rather than hardcoding keeps this safe against a future re-export.
		box_max = boxes_raw.max() if boxes_raw.size else 0.0
		if box_max > 1.5:
			input_h, input_w = self.original_h, self.original_w
			boxes_xyxy = boxes_raw / np.array([input_w, input_h, input_w, input_h], dtype=np.float32)
		else:
			boxes_xyxy = boxes_raw

		# Read thresholds from custom parameters (updated each frame)
		self.conf_threshold = self._par_or_default('Confthreshold', CONF_THRESHOLD)
		self.low_conf_threshold = self._par_or_default('Lowconfthreshold', LOW_CONF_THRESHOLD)
		nms_iou_threshold = self._par_or_default('Nmsiouthreshold', NMS_IOU_THRESHOLD)
		min_box_width = self._par_or_default('Minboxwidth', MIN_BOX_WIDTH)
		min_box_height = self._par_or_default('Minboxheight', MIN_BOX_HEIGHT)
		min_mask_area_ratio = self._par_or_default('Minmaskarea', MIN_MASK_AREA_RATIO)
		mask_threshold = self._par_or_default('Maskthreshold', MASK_THRESHOLD)
		self.tracker.high_thresh = self.conf_threshold
		self.tracker.low_thresh = self.low_conf_threshold
		self.tracker.match_thresh = self._par_or_default('Trackiouthreshold', TRACKER_IOU_THRESHOLD)
		self.tracker.track_buffer = self._par_or_default('Tracklossframes', TRACKER_MAX_AGE)
		self.tracker.min_hits = int(self._par_or_default('Trackconfirmframes', TRACKER_MIN_HITS))
		smoothing = self._par_or_default('Outputsmoothing', OUTPUT_SMOOTHING)

		# Keep everything down to the LOW threshold -- ByteTracker does its own high/low
		# split internally for the two-stage association, so pre-filtering to the high
		# threshold here would defeat the low-confidence recovery pass entirely.
		valid = confidences > self.low_conf_threshold
		valid &= (boxes_xyxy[:, 2] - boxes_xyxy[:, 0] >= min_box_width) & (boxes_xyxy[:, 3] - boxes_xyxy[:, 1] >= min_box_height)
		if self._target_ids_array is not None and len(self._target_ids_array) > 0:
			valid &= np.isin(class_ids, self._target_ids_array)

		boxes_xyxy = boxes_xyxy[valid]
		confidences = confidences[valid]
		class_ids = class_ids[valid]
		mask_coeffs = mask_coeffs[valid]

		# Clip boxes to [0, 1]
		boxes_xyxy = np.clip(boxes_xyxy, 0.0, 1.0)

		# Keep a copy in the model's NATIVE (pre-TD-flip) orientation, carried through the
		# same NMS keep-indexing below -- needed to crop each decoded mask to its own box
		# region (see mask-crop comment), since mask_protos is decoded in that same native
		# top-down orientation and never gets TD's Y-flip applied to it.
		boxes_native = boxes_xyxy.copy()

		# Flip Y-axis for TouchDesigner (model uses top-down, TD uses bottom-up)
		boxes_xyxy[:, 1], boxes_xyxy[:, 3] = 1.0 - boxes_xyxy[:, 3], 1.0 - boxes_xyxy[:, 1]

		# Collapse near-duplicate detections before they ever reach the tracker.
		if len(boxes_xyxy) > 0:
			keep = _nms(boxes_xyxy, confidences, nms_iou_threshold)
			boxes_xyxy = boxes_xyxy[keep]
			boxes_native = boxes_native[keep]
			confidences = confidences[keep]
			class_ids = class_ids[keep]
			mask_coeffs = mask_coeffs[keep]

		# Build detection list for the tracker. Mask decode (coefficients x prototypes
		# matmul) only runs on these NMS survivors -- the single most expensive step here,
		# so it never touches the full 300-candidate pool.
		detections = []
		if len(boxes_xyxy) > 0:
			masks = np.matmul(mask_coeffs, mask_protos.reshape(num_mask_coeffs, -1)).reshape(-1, proto_h, proto_w)
			np.negative(masks, out=masks)
			np.exp(masks, out=masks)
			np.add(1.0, masks, out=masks)
			np.reciprocal(masks, out=masks)
			binary_masks = masks > mask_threshold

			# Crop each mask to its own detection box (standard YOLO-seg postprocessing --
			# Ultralytics' own pipeline does this too). The coefficient x prototype decode
			# is a loose, global-ish activation map; without confining it to the box that
			# actually produced it, stray activations elsewhere in the frame (background
			# texture, a different person, etc.) show through as noise that has nothing to
			# do with this instance. Box coords are normalized 0-1 in the mask's own native
			# (pre-TD-flip) orientation -- see boxes_native comment above.
			px1 = np.clip((boxes_native[:, 0] * proto_w).astype(np.intp), 0, proto_w)
			py1 = np.clip((boxes_native[:, 1] * proto_h).astype(np.intp), 0, proto_h)
			px2 = np.clip(np.ceil(boxes_native[:, 2] * proto_w).astype(np.intp), 0, proto_w)
			py2 = np.clip(np.ceil(boxes_native[:, 3] * proto_h).astype(np.intp), 0, proto_h)
			col_idx = np.arange(proto_w)
			row_idx = np.arange(proto_h)
			box_areas_px = np.maximum((px2 - px1) * (py2 - py1), 1)  # each box's own pixel area at proto res
			for i in range(len(binary_masks)):
				col_in_box = (col_idx >= px1[i]) & (col_idx < px2[i])
				row_in_box = (row_idx >= py1[i]) & (row_idx < py2[i])
				in_box = row_in_box[:, np.newaxis] & col_in_box[np.newaxis, :]
				binary_masks[i] &= in_box
				masks[i] *= in_box  # zero soft probabilities outside the box too -- same reasoning

			mask_areas = binary_masks.sum(axis=(1, 2))
			# Ratio of the box's OWN area filled, not a fraction of the whole frame canvas --
			# scale-invariant regardless of how near/far a person is (a distant person's box
			# is naturally tiny in absolute pixels; a fixed frame-fraction threshold would
			# reject them even when their mask fills that small box perfectly well). A real
			# person's silhouette typically fills something like 35-70% of their own box
			# (limb gaps keep it well under 100%); a much lower fill fraction usually means a
			# degenerate/noisy mask that just happens to share a box with a real detection.
			fill_ratios = mask_areas / box_areas_px

			for i in range(len(boxes_xyxy)):
				if fill_ratios[i] <= min_mask_area_ratio:
					continue
				detections.append({
					'box': boxes_xyxy[i].tolist(),
					'score': float(confidences[i]),
					'class_id': int(class_ids[i]),
					'class_name': COCO_CLASSES.get(int(class_ids[i]), 'unknown'),
					# Soft (pre-threshold) probability, box-cropped -- NOT the hard binary
					# mask, so the visual composite has continuous values for TD's own
					# downstream upscale to interpolate smoothly (see class docstring).
					# mask_threshold/fill_ratios above (from binary_masks) still gate
					# acceptance -- this is purely what gets carried through for display.
					'mask': masks[i],
					'mask_area_ratio': float(fill_ratios[i]),
				})

		# Update tracker (runs on main thread, no lock needed)
		active_tracks = self.tracker.update(detections)

		# Build structured data for CHOP/table output (filter out decayed/unconfirmed tracks)
		active_ids = {t.track_id for t in active_tracks}
		self.tracked_objects = []
		for t in active_tracks:
			# t.confirmed gates display, same reasoning as the score check just below --
			# a track still in its min_hits confirmation window is genuinely "alive" (kept
			# in active_ids, keeps its tracker-side Kalman/box/mask state) but not yet
			# trusted as a real person, exactly like a track kept alive only by
			# low-confidence recovery.
			if t.score < self.conf_threshold or not t.confirmed:
				continue
			box = t.box  # Kalman estimate
			smoothed = object_tracker.box_smooth(self._box_state, t.track_id, box, smoothing)

			# Masks aren't smoothed pixel-wise -- hold the last real decoded mask across
			# any frame this track didn't get a fresh detection (see class docstring).
			new_mask = t.payload.get('mask')
			if new_mask is not None:
				self._mask_state[t.track_id] = new_mask
			held_mask = self._mask_state.get(t.track_id)

			cx = (smoothed[0] + smoothed[2]) / 2
			cy = (smoothed[1] + smoothed[3]) / 2
			w = smoothed[2] - smoothed[0]
			h = smoothed[3] - smoothed[1]
			self.tracked_objects.append({
				'track_id': t.track_id,
				'class_id': t.payload.get('class_id'),
				'class_name': t.payload.get('class_name', 'unknown'),
				'score': t.score,
				'cx': cx, 'cy': cy, 'w': w, 'h': h,
				'x_left': smoothed[0],
				'x_right': smoothed[2],
				'y_top': smoothed[3],     # top edge of bbox (TD coords)
				'y_bottom': smoothed[1],  # bottom edge of bbox (TD coords)
				'vx': float(t.mean[4]), 'vy': float(t.mean[5]),  # Kalman-estimated box-center velocity
				'lost_frames': t.lost_frames,
				'total_frames': t.total_frames,
				'mask_area_ratio': t.payload.get('mask_area_ratio', 0.0),
				'mask': held_mask,
			})

		# Prune box/mask state for tracks the tracker has dropped entirely.
		object_tracker.prune_stale(active_ids, self._box_state, self._mask_state)

		# Draw output image. Unlike onnx_yolo26_pose.py/onnx_yolo26_obj_det.py -- where the
		# boxes/skeleton are an optional debug view over the real product (track DATA,
		# output via table_output) -- the segmented mask IS this script's actual product.
		# Gating it behind DRAW_BOXES (default off) would make the script output a black
		# frame by default, which defeats the point of a segmentation runner. So masks
		# always render; DRAW_BOXES/Drawdebug only controls the optional box-outline/
		# track-label overlay on top of them.
		output_img = self.npu.flip_v(self.draw_tracked_masks(draw_labels=DRAW_BOXES))

		return output_img

	def on_result_published(self):
		"""Flush table_output from tracked_objects right after this frame's texture
		publishes, before the next frame's capture/dispatch -- see
		ONNXInferenceManager.on_result_published()'s docstring. Gated by Outputtrackdata
		since this is pure "data output" overhead separate from the visual matte (see
		OUTPUT_TRACK_DATA comment)."""
		if self._par_or_default('Outputtrackdata', OUTPUT_TRACK_DATA):
			self.write_tracks_to_table()

	def draw_tracked_masks(self, draw_labels=False):
		"""Render a soft-edged white silhouette matte for currently (this-frame) detected
		people at the mask prototype's NATIVE resolution -- no upscaling here (see class
		docstring: that belongs downstream in TD's own GPU pipeline). The composite stays
		as continuous (pre-threshold) probabilities rather than a hard binary mask, so
		whatever upscales it afterward has real values to interpolate into a smooth edge.
		Lost/occluded tracks are NOT drawn (their held mask doesn't move, so drawing it
		would paint a stale ghost -- see postprocess()'s _mask_state comment). draw_labels
		additionally overlays per-track colored box outlines + a compact track id label,
		directly at this native resolution (small and blocky at this size -- a debug aid,
		not meant to be read without TD's own upscale on top). Returns an RGB float32
		(0-1) image at proto resolution."""
		proto_h, proto_w = self._proto_h, self._proto_w
		composite = np.zeros((proto_h, proto_w), dtype=np.float32)
		for obj in self.tracked_objects:
			# Only draw a FRESHLY detected mask this frame (lost_frames == 0) -- a lost
			# track's mask is held in _mask_state (see postprocess()) but doesn't move,
			# so drawing it here would paint a frozen ghost at the person's last known
			# position instead of reflecting who's actually visible right now, i.e.
			# exactly the trailing/ghosting artifact this is written to avoid.
			if obj['lost_frames'] > 0:
				continue
			mask = obj.get('mask')
			if mask is None:
				continue
			# Per-pixel max, not overwrite -- composite is a single soft intensity
			# (white), not per-track color, so taking the brighter of two overlapping
			# instances' probabilities at a shared pixel is exactly correct.
			np.maximum(composite, mask, out=composite)

		composite = np.clip(composite, 0.0, 1.0)
		composite_rgb = np.repeat(composite[:, :, np.newaxis], 3, axis=2)

		if not draw_labels:
			return composite_rgb

		# Work in uint8 BGR for cv2 box/label drawing, then convert back.
		draw_img = cv2.cvtColor((composite_rgb * 255).astype(np.uint8), cv2.COLOR_RGB2BGR)

		def to_px(td_x, td_y):
			"""TD-normalized coords (y: 0=bottom, 1=top) -> pixel (col, row) in this
			function's plain top-down array (row 0 = top); flipped back to TD's
			bottom-up convention afterward (see postprocess())."""
			return object_tracker.td_to_px(td_x, td_y, proto_w, proto_h)

		for obj in self.tracked_objects:
			if obj['lost_frames'] > 0 and obj['score'] < self.conf_threshold * 0.5:
				continue

			px1, py_bottom = to_px(obj['x_left'], obj['y_bottom'])
			px2, py_top = to_px(obj['x_right'], obj['y_top'])

			color_f = _track_color(obj['track_id'])
			color_bgr = (int(color_f[2] * 255), int(color_f[1] * 255), int(color_f[0] * 255))
			if obj['lost_frames'] > 0:
				fade = object_tracker.track_fade(obj['lost_frames'], self.tracker.track_buffer)
				color_bgr = tuple(int(c * fade) for c in color_bgr)

			cv2.rectangle(draw_img, (px1, py_top), (px2, py_bottom), color_bgr, 1)
			cv2.putText(draw_img, f"#{obj['track_id']}", (px1, max(py_top - 2, 8)),
				cv2.FONT_HERSHEY_SIMPLEX, 0.3, color_bgr, 1, cv2.LINE_AA)

		# Convert BGR uint8 -> RGB float32 (0-1)
		return cv2.cvtColor(draw_img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0

	# ==================== CHOP TRACKING OUTPUT ====================
	# To output tracking data to a CHOP, use a Script CHOP DAT with:
	#
	#   mgr = op('script1').module.inference_manager
	#   tracks = mgr.tracked_objects  # list of dicts
	#
	# Each dict contains: track_id, class_id, class_name, score,
	#   cx, cy, w, h, x_left, x_right, y_top, y_bottom, vx, vy (Kalman-estimated),
	#   lost_frames, total_frames, mask_area_ratio, mask (proto-res bool array)
	#
	# For a Table DAT approach, call write_tracks_to_table() from a
	# Script DAT or Execute DAT each frame.

	def write_tracks_to_table(self):
		"""Helper to write current tracking data to a Table DAT.
		Call from an Execute DAT's onFrameStart or a Timer callback.
		tracked_objects already holds smoothed box values (see postprocess()'s
		self._box_state lerp), so this just formats them -- no smoothing happens here.
		The mask array itself isn't written here (too large for a table cell) -- only
		its area ratio, as a cheap useful summary stat."""
		tbl = self.opOutputTableDAT
		if tbl is None:
			return

		tbl.clear()
		tbl.appendRow([
			*object_tracker.label_header(),
			'class_id', 'class_name',
			*object_tracker.box_header(),
			'mask_area_ratio',
			*object_tracker.color_header(),
		])
		for obj in self.tracked_objects:
			tbl.appendRow([
				*object_tracker.label_row(obj['track_id'], obj['score']),
				obj['class_id'], obj['class_name'],
				*object_tracker.box_row(obj),
				f"{obj['mask_area_ratio']:.4f}",
				*object_tracker.color_row(obj['track_id']),
			])


# Create global instance -- shut down any PREVIOUS instance first (releases its
# GPU-resident ONNX Runtime session(s) and stops its worker thread) so a script
# reload during active development doesn't leak both -- see
# onnx_inference_manager.shutdown_and_register()'s docstring for the full
# mechanism this avoids (and why it's NOT TD's own store()/fetch(), which risked
# a real crash trying to persist a live, unpicklable manager instance).
inference_manager = YOLO26SegmentationInference()
onnx_inference_manager.shutdown_and_register(parent().path, inference_manager)

# Kick the model load off without waiting for TD's pull-based cooking to ever give script1 a
# cook request on its own -- nothing wires this COMP's output downstream by default, so
# without this, script1 would never cook (and the model would never load) until something
# visits/views/wires it. See ONNXInferenceManager.schedule_prewarm_cook()'s docstring for why
# this has to go through a deferred td.run() rather than a direct cook(force=True) call here.
inference_manager.schedule_prewarm_cook(op('script1'), me)

# TouchDesigner callback wrappers that delegate to the manager
def onSetupParameters(scriptOp):
	return inference_manager.onSetupParameters(scriptOp)


def onPulse(par):
	return inference_manager.onPulse(par)


def onCook(scriptOp):
	# Run base manager cook (handles model loading, inference dispatch, copyNumpyArray)
	inference_manager.onCook(scriptOp)

	# Optionally draw masks/boxes on main thread to avoid threading issues with OpenCV (if enabled)
	global DRAW_BOXES
	DRAW_BOXES = parent().par.Drawdebug.eval() == 1

	# Table writes happen inside inference_manager.onCook(scriptOp) above now, via
	# on_result_published() (still gated by Outputtrackdata internally).


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
	skip instead lives in ONNXInferenceManager.onCook() itself (checks scriptOp.time.play
	and returns early), which keeps this op always eligible to cook every frame so the
	very next real cook after resuming naturally picks back up.
	"""

	return CookLevel.ALWAYS
