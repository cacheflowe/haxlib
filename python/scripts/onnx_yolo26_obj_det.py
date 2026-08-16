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

# Class-specific colors (BGR 0-255 for cv2 drawing)
CLASS_COLORS_BGR = {
	'person': (0, 255, 0),        # Green
	'car': (0, 0, 255),           # Red
	'bicycle': (255, 0, 0),       # Blue
	'dog': (0, 255, 255),         # Yellow
	'cat': (0, 128, 255),         # Orange
	'chair': (255, 0, 128),       # Purple
	'bottle': (255, 255, 0),      # Cyan
}
DEFAULT_COLOR_BGR = (255, 255, 255)  # White fallback

# ==================== CONFIGURATION ====================
# Classes to detect (empty list = detect ALL 80 COCO classes). NOTE: ByteTracker's
# matching is class-agnostic (pure IoU on boxes), so it can match a detection to an
# existing track of a different class if their boxes overlap enough. Only safe as long
# as this stays a single class. If ever widened to multiple classes, add a per-class
# partition before calling tracker.update() (one ByteTracker per class, or make
# cross-class pairs infinitely costly in the assignment).
CLASSES_TO_DETECT = ['person']  # e.g. ['person', 'car', 'dog']

# Which model variant to use: 'yolo26n' (faster) or 'yolo26s' (more accurate)
# NOTE: For best performance, export directly from Ultralytics rather than using
# onnx-community HuggingFace models. The HF models use a DETR transformer decoder
# which is much slower. To export the fast anchor-based model:
#
#   pip install ultralytics
#   python -c "from ultralytics import YOLO; YOLO('yolo26n.pt').export(format='onnx', imgsz=640, simplify=True)"
#
# Then place yolo26n.onnx in data/ml/models/yolo26/
# The script auto-detects DETR vs YOLO output format.
MODEL_VARIANT = 'yolo26n'

# Confidence threshold for a detection to be shown/tracked (0.0 - 1.0). This is
# ByteTracker's "high confidence" threshold -- detections at or above this score are
# matched first and can start brand-new tracks.
CONF_THRESHOLD = 0.5

# ByteTracker's "low confidence" threshold. Detections scoring between this and
# CONF_THRESHOLD are never used to start a new track, but ARE used in a second
# association pass to recover existing tracks that a plain confidence-thresholded
# detector would otherwise drop (occlusion, motion blur, partial visibility) -- this is
# ByteTrack's actual innovation. Detections below this are discarded as background.
# Kept as a separate value from CONF_THRESHOLD here (unlike onnx_yolo26_pose.py, which
# collapses the two for reasons specific to that model/scene) -- tune independently.
LOW_CONF_THRESHOLD = 0.1

# IoU threshold for NMS applied to raw per-frame detections before tracking (lower =
# more aggressive suppression). See object_tracker.nms().
NMS_IOU_THRESHOLD = 0.45

# Minimum box width/height (normalized 0-1, fraction of frame dimension) for a detection
# to be kept at all -- applied alongside Confthreshold, before NMS/tracking. A tiny,
# degenerate box is almost never a real object regardless of its confidence score.
# Separate width/height floors, NOT one shared value applied to both axes -- an object
# (e.g. a standing person) is rarely square, so a single shared threshold high enough to
# reject small-on-both-axes noise ends up incorrectly rejecting real objects that are
# just proportionally narrow on one axis. Tune independently.
MIN_BOX_WIDTH = 0.02
MIN_BOX_HEIGHT = 0.02

# Tracker: max frames to keep a lost track alive
TRACKER_MAX_AGE = 30

# Tracker: min IoU to accept a match between a track and a detection
TRACKER_IOU_THRESHOLD = 0.3

# Tracker: total matched frames (not necessarily consecutive -- see object_tracker.Track's
# confirmed/hits) a brand-new track needs before it's confirmed and shown/output at all.
# Filters out single-frame noise "detections" that rarely get a second match before
# track_buffer prunes them. Costs a few frames of extra latency on a genuinely new
# object's first appearance; once confirmed, a track stays confirmed through brief
# occlusion (that's Tracklossframes' job, not this one).
TRACKER_MIN_HITS = 3

# Smoothing factor for box position/size lerp (0 = no smoothing, 1 = frozen). ByteTracker's
# Kalman filter already smooths motion *prediction*, but a matched detection still snaps
# the estimate fairly tightly toward the raw box each time -- this adds an extra lerp on
# top (same role Outputsmoothing plays for keypoints in onnx_yolo26_pose.py).
OUTPUT_SMOOTHING = 0.5

# Draw bounding boxes on the output image?
DRAW_BOXES = False


# ==================== YOLO26 OBJECT DETECTION ====================

class YOLO26ObjectDetectionInference(ONNXInferenceManager):
	"""YOLO26 Object Detection inference with temporal tracking.

	Supports onnx-community HuggingFace models (DETR-style: 300 queries)
	and standard Ultralytics ONNX exports (anchor-based: 8400 candidates).
	The output format is auto-detected at model load time.

	Tracking uses `object_tracker.ByteTracker` (shared across every ONNX script in this
	project) for the full box-tracking lifecycle -- Kalman motion prediction, optimal
	(Hungarian) assignment, and ByteTrack's two-stage high/low-confidence association.
	Box position/size is smoothed on top of the tracker's own Kalman estimate (see
	OUTPUT_SMOOTHING/self._box_state); class_id/class_name are categorical and just ride
	along in the track's payload unchanged, nothing to smooth there.
	"""

	def __init__(self):
		super().__init__()
		self.opOutputTableDAT = parent().op('table_output')  # Optional Table DAT for structured output
		self.output_format = None  # 'detr' or 'yolo' - detected at load
		self.num_classes = 80
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
		# Structured tracking data exposed for CHOP consumption
		# Each entry: {track_id, class_id, class_name, score, cx, cy, w, h, x_left, x_right, y_top, y_bottom, vx, vy, lost_frames, total_frames}
		self.tracked_objects = []
		# Pre-allocated buffers (lazily sized)
		self._output_buf = None
		self._output_buf_shape = None
		self._input_tensor_buf = None   # pre-allocated NCHW input buffer
		self._input_buf_shape = None
		# Cache target class IDs
		self._target_ids_array = np.array([idx for idx, name in COCO_CLASSES.items() if name in CLASSES_TO_DETECT], dtype=np.intp) if CLASSES_TO_DETECT else None

	def onSetupParameters(self, scriptOp):
		"""Add YOLO26-specific parameters alongside base class params."""
		super().onSetupParameters(scriptOp)
		page = scriptOp.appendCustomPage('YOLO26')
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
		p[0].help = object_tracker.par_help('Nmsiouthreshold')
		scriptOp.par.Nmsiouthreshold = NMS_IOU_THRESHOLD
		p = page.appendFloat('Minboxwidth', label='Min Box Width', size=1)
		p[0].default = MIN_BOX_WIDTH
		p[0].min = 0.0
		p[0].max = 0.2
		p[0].clampMin = True
		p[0].clampMax = False
		p[0].help = object_tracker.par_help('Minboxwidth', shape_note=(
			"an object is rarely square, so one shared threshold high enough to reject noise ends up "
			"rejecting real objects that are just proportionally narrow on one axis."
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
		p[0].help = object_tracker.par_help('Tracklossframes')
		scriptOp.par.Tracklossframes = TRACKER_MAX_AGE
		p = page.appendFloat('Trackiouthreshold', label='Track IoU Threshold', size=1)
		p[0].default = TRACKER_IOU_THRESHOLD
		p[0].min = 0.0
		p[0].max = 1.0
		p[0].clampMin = True
		p[0].clampMax = True
		p[0].help = object_tracker.par_help('Trackiouthreshold')
		scriptOp.par.Trackiouthreshold = TRACKER_IOU_THRESHOLD
		p = page.appendFloat('Trackconfirmframes', label='Track Confirm Frames', size=1)
		p[0].default = TRACKER_MIN_HITS
		p[0].min = 1.0
		p[0].max = 30.0  # tuned default is 3 -- a handful of frames, not tens
		p[0].clampMin = True
		p[0].clampMax = False
		p[0].help = object_tracker.par_help('Trackconfirmframes')
		scriptOp.par.Trackconfirmframes = TRACKER_MIN_HITS
		p = page.appendFloat('Outputsmoothing', label='Output Smoothing', size=1)
		p[0].default = OUTPUT_SMOOTHING
		p[0].min = 0.0
		p[0].max = 1.0
		p[0].clampMin = True
		p[0].clampMax = True
		p[0].help = object_tracker.par_help('Outputsmoothing')
		scriptOp.par.Outputsmoothing = OUTPUT_SMOOTHING

	def get_model_path(self):
		"""Return path to YOLO26 detection model."""
		# Models from:
		# - https://huggingface.co/onnx-community/yolo26n-ONNX/tree/main/onnx
		# - https://huggingface.co/onnx-community/yolo26s-ONNX/tree/main/onnx
		model_dir = os.path.join(project.folder, 'data', 'ml', 'yolo26')
		return os.path.join(model_dir, f'{MODEL_VARIANT}.onnx')

	def on_model_loaded(self, session):
		"""Inspect model outputs to determine format (DETR vs traditional YOLO)."""
		outputs = session.get_outputs()
		self.printONNX(f"YOLO26 model outputs ({len(outputs)}):")
		for i, o in enumerate(outputs):
			self.printONNX(f"  [{i}] name='{o.name}' shape={o.shape} type={o.type}")

		inputs = session.get_inputs()
		for i, inp in enumerate(inputs):
			self.printONNX(f"  input[{i}] name='{inp.name}' shape={inp.shape} type={inp.type}")

		# Log active execution providers (critical for performance diagnosis)
		self.check_providers(session)

		# Auto-detect output format
		if len(outputs) == 2:
			# DETR-style: logits [1, 300, 80] + pred_boxes [1, 300, 4]
			self.output_format = 'detr'
			self.printONNX("Detected DETR-style output format (300 queries)")
		elif len(outputs) == 1:
			shape = outputs[0].shape
			# Traditional YOLO: [1, 84, 8400] or [1, 8400, 84]
			if shape and len(shape) == 3:
				if shape[1] == 84 or shape[2] == 84:
					self.output_format = 'yolo'
					self.printONNX(f"Detected traditional YOLO output format {shape}")
				else:
					self.output_format = 'yolo'
					self.printONNX(f"Assuming YOLO format for shape {shape}")
			else:
				self.output_format = 'yolo'
				self.printONNX(f"Unknown shape {shape}, defaulting to YOLO format")
		else:
			self.output_format = 'detr'
			self.printONNX(f"Unknown output count {len(outputs)}, trying DETR format")

	def preprocess(self, nA):
		"""Preprocess input for YOLO26 detection model.
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

	def _parse_detr_outputs(self, outputs):
		"""Parse DETR-style outputs: logits + pred_boxes (onnx-community format)."""
		logits = outputs[0][0]     # (300, 80) raw logits
		pred_boxes = outputs[1][0] # (300, 4)  normalized [cx, cy, w, h]

		# Sigmoid to get class probabilities (in-place to avoid allocation)
		np.negative(logits, out=logits)
		np.exp(logits, out=logits)
		np.add(1.0, logits, out=logits)
		np.reciprocal(logits, out=logits)  # logits now contains sigmoid scores

		class_ids = np.argmax(logits, axis=1)    # (300,)
		confidences = np.max(logits, axis=1)     # (300,)

		# Convert [cx, cy, w, h] normalized -> [x1, y1, x2, y2] normalized (in-place)
		half_w = pred_boxes[:, 2] * 0.5
		half_h = pred_boxes[:, 3] * 0.5
		cx = pred_boxes[:, 0]
		cy = pred_boxes[:, 1]
		boxes_xyxy = np.column_stack([cx - half_w, cy - half_h, cx + half_w, cy + half_h])

		return boxes_xyxy, class_ids, confidences

	def _parse_yolo_outputs(self, outputs):
		"""Parse traditional YOLO output: [1, 84, N] or [1, N, 84]."""
		pred = outputs[0][0]  # (84, N) or (N, 84)

		# Determine orientation: 84 classes+boxes dimension
		if pred.shape[0] == 4 + self.num_classes:
			# (84, N) -> transpose to (N, 84)
			pred = pred.T
		# Now pred is (N, 84): first 4 = xywh, rest = class scores

		boxes_xywh = pred[:, :4]  # (N, 4) center_x, center_y, w, h in pixels (input space)
		class_scores = pred[:, 4:]  # (N, 80)

		class_ids = np.argmax(class_scores, axis=1)
		confidences = np.max(class_scores, axis=1)

		# Convert xywh (pixel space) -> xyxy normalized 0-1
		input_h, input_w = self.original_h, self.original_w
		cx, cy, w, h = boxes_xywh[:, 0], boxes_xywh[:, 1], boxes_xywh[:, 2], boxes_xywh[:, 3]
		x1 = (cx - w / 2) / input_w
		y1 = (cy - h / 2) / input_h
		x2 = (cx + w / 2) / input_w
		y2 = (cy + h / 2) / input_h
		boxes_xyxy = np.stack([x1, y1, x2, y2], axis=1)

		return boxes_xyxy, class_ids, confidences

	def postprocess(self, outputs):
		"""Postprocess YOLO26 detection outputs.

		Parses model output (auto-detected format), applies class filtering,
		confidence thresholding, NMS, tracking, and draws bounding boxes.
		"""
		# Parse outputs based on detected format
		if self.output_format == 'detr':
			boxes_xyxy, class_ids, confidences = self._parse_detr_outputs(outputs)
		else:
			boxes_xyxy, class_ids, confidences = self._parse_yolo_outputs(outputs)

		# Read thresholds from custom parameters (updated each frame)
		self.conf_threshold = self._par_or_default('Confthreshold', CONF_THRESHOLD)
		self.low_conf_threshold = self._par_or_default('Lowconfthreshold', LOW_CONF_THRESHOLD)
		nms_iou_threshold = self._par_or_default('Nmsiouthreshold', NMS_IOU_THRESHOLD)
		self.tracker.high_thresh = self.conf_threshold
		self.tracker.low_thresh = self.low_conf_threshold
		self.tracker.match_thresh = self._par_or_default('Trackiouthreshold', TRACKER_IOU_THRESHOLD)
		self.tracker.track_buffer = self._par_or_default('Tracklossframes', TRACKER_MAX_AGE)
		self.tracker.min_hits = int(self._par_or_default('Trackconfirmframes', TRACKER_MIN_HITS))
		smoothing = self._par_or_default('Outputsmoothing', OUTPUT_SMOOTHING)
		min_box_width = self._par_or_default('Minboxwidth', MIN_BOX_WIDTH)
		min_box_height = self._par_or_default('Minboxheight', MIN_BOX_HEIGHT)

		# Keep everything down to the LOW threshold -- ByteTracker does its own high/low
		# split internally for the two-stage association, so pre-filtering to the high
		# threshold here would defeat the low-confidence recovery pass entirely.
		valid = confidences > self.low_conf_threshold
		# Reject degenerate tiny boxes regardless of confidence -- see MIN_BOX_WIDTH/HEIGHT
		# comment for why these are separate thresholds, not one shared value.
		valid &= (boxes_xyxy[:, 2] - boxes_xyxy[:, 0] >= min_box_width) & (boxes_xyxy[:, 3] - boxes_xyxy[:, 1] >= min_box_height)

		# Class filter (vectorized) -- see CLASSES_TO_DETECT comment on why this keeps
		# ByteTracker's class-agnostic matching safe for the current person-only use.
		if self._target_ids_array is not None and len(self._target_ids_array) > 0:
			valid &= np.isin(class_ids, self._target_ids_array)

		boxes_xyxy = boxes_xyxy[valid]
		class_ids = class_ids[valid]
		confidences = confidences[valid]

		# Clip boxes to [0, 1]
		boxes_xyxy = np.clip(boxes_xyxy, 0.0, 1.0)

		# Flip Y-axis for TouchDesigner (model uses top-down, TD uses bottom-up)
		boxes_xyxy[:, 1], boxes_xyxy[:, 3] = 1.0 - boxes_xyxy[:, 3], 1.0 - boxes_xyxy[:, 1]

		# Collapse near-duplicate detections before they ever reach the tracker.
		if len(boxes_xyxy) > 0:
			keep = _nms(boxes_xyxy, confidences, nms_iou_threshold)
			boxes_xyxy = boxes_xyxy[keep]
			class_ids = class_ids[keep]
			confidences = confidences[keep]

		# Build detection list for the tracker. No detection-count cap here: the
		# tracker itself (ByteTracker.max_detections) is what bounds worst-case cost.
		detections = []
		for i in range(len(boxes_xyxy)):
			detections.append({
				'box': boxes_xyxy[i].tolist(),
				'score': float(confidences[i]),
				'class_id': int(class_ids[i]),
				'class_name': COCO_CLASSES.get(int(class_ids[i]), 'unknown'),
			})

		# Update tracker (runs on main thread, no lock needed)
		active_tracks = self.tracker.update(detections)

		# Build structured data for CHOP output (filter out decayed tracks)
		active_ids = {t.track_id for t in active_tracks}
		self.tracked_objects = []
		for t in active_tracks:
			# t.confirmed gates display, same reasoning as the score check just below --
			# a track still in its min_hits confirmation window is genuinely "alive" (kept
			# in active_ids, keeps its tracker-side Kalman/box-smoothing state) but not yet
			# trusted as a real object, exactly like a track kept alive only by
			# low-confidence recovery.
			if t.score < self.conf_threshold or not t.confirmed:
				continue
			box = t.box  # Kalman estimate
			smoothed = object_tracker.box_smooth(self._box_state, t.track_id, box, smoothing)

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
			})

		# Prune box-smoothing state for tracks the tracker has dropped entirely.
		object_tracker.prune_stale(active_ids, self._box_state)

		# Draw output image
		if DRAW_BOXES:
			output_img = self.npu.flip_v(self.draw_tracked_boxes())
		else:
			# Black frame â€” no need to zero or flip each frame, just reuse static buffer
			needed_shape = (self.original_h, self.original_w, 3)
			if self._output_buf is None or self._output_buf_shape != needed_shape:
				self._output_buf = np.zeros(needed_shape, dtype=np.float32)
				self._output_buf_shape = needed_shape
			output_img = self._output_buf

		return output_img

	def on_result_published(self):
		"""Flush table_output from tracked_objects right after this frame's texture
		publishes, before the next frame's capture/dispatch -- see
		ONNXInferenceManager.on_result_published()'s docstring."""
		self.write_tracks_to_table()

	def draw_tracked_boxes(self):
		"""Render bounding boxes for tracked objects onto a blank image.
		Returns an RGB float32 (0-1) image at original resolution."""
		output_img = np.zeros((self.original_h, self.original_w, 3), dtype=np.float32)

		if not self.tracked_objects:
			return output_img

		# Work in uint8 for cv2 drawing, then convert back
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

			class_name = obj['class_name']
			color = CLASS_COLORS_BGR.get(class_name, DEFAULT_COLOR_BGR)

			# Dim color if track is unmatched (age > 0)
			if obj['lost_frames'] > 0:
				fade = object_tracker.track_fade(obj['lost_frames'], self.tracker.track_buffer)
				color = tuple(int(c * fade) for c in color)

			thickness = 2
			cv2.rectangle(draw_img, (px1, py_top), (px2, py_bottom), color, thickness)

			label = f"#{obj['track_id']} {class_name} {obj['score']:.0%}"
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
	# Each dict contains: track_id, class_id, class_name, score,
	#   cx, cy, w, h, x_left, x_right, y_top, y_bottom, vx, vy (Kalman-estimated),
	#   lost_frames, total_frames
	#
	# For a Table DAT approach, call write_tracks_to_table() from a
	# Script DAT or Execute DAT each frame.

	def write_tracks_to_table(self):
		"""Helper to write current tracking data to a Table DAT.
		Call from an Execute DAT's onFrameStart or a Timer callback.
		tracked_objects already holds smoothed box values (see postprocess()'s
		self._box_state lerp), so this just formats them -- no smoothing happens here."""
		tbl = self.opOutputTableDAT
		if tbl is None:
			return

		tbl.clear()
		tbl.appendRow([
			*object_tracker.label_header(),
			'class_id', 'class_name',
			*object_tracker.box_header(),
			*object_tracker.color_header(),
		])
		for obj in self.tracked_objects:
			tbl.appendRow([
				*object_tracker.label_row(obj['track_id'], obj['score']),
				obj['class_id'], obj['class_name'],
				*object_tracker.box_row(obj),
				*object_tracker.color_row(obj['track_id']),
			])


# Create global instance -- shut down any PREVIOUS instance first (releases its
# GPU-resident ONNX Runtime session(s) and stops its worker thread) so a script reload
# during active development doesn't leak both. See Round 7/8 in
# td-threaded-inference-optimization.md and shutdown_and_register()'s docstring.
inference_manager = YOLO26ObjectDetectionInference()
onnx_inference_manager.shutdown_and_register(parent().path, inference_manager)

# TouchDesigner callback wrappers that delegate to the manager
def onSetupParameters(scriptOp):
	return inference_manager.onSetupParameters(scriptOp)


def onPulse(par):
	return inference_manager.onPulse(par)


def onCook(scriptOp):
	# Run base manager cook (handles model loading, inference dispatch, copyNumpyArray).
	# Table writes happen inside this call now, via on_result_published() -- called
	# right after this frame's texture publishes, before the next frame's capture gets
	# dispatched.
	inference_manager.onCook(scriptOp)

	# Optionally draw boxes on main thread to avoid threading issues with OpenCV (if enabled)
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

	AUTOMATIC alone can't drive this pipeline reliably: anything reading tracked_objects
	via a raw Python module reference (not a wire/parameter) is invisible to TD's "is the
	output being used" dependency check, so AUTOMATIC can stop cooking this even while
	something downstream still depends on it. Worse, once AUTOMATIC settles into "not
	cooking" nothing prompts it to re-check later -- resuming play isn't a registered
	dependency of this op, so it never recovers on its own. Always returning ALWAYS keeps
	this op eligible to cook every frame; the play/pause skip instead lives in
	ONNXInferenceManager.onCook() itself (checks scriptOp.time.play and returns early), so
	the very next real cook after resuming naturally picks back up.
	"""

	return CookLevel.ALWAYS
