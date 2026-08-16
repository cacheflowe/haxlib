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
_track_color = object_tracker.track_color

# ==================== CONFIGURATION ====================
# This runner is dedicated to PEOPLE segmentation via RF-DETR (rf-detr-seg-small.onnx from
# https://github.com/PierreMarieCurie/rf-detr-onnx), the same restriction and reasoning as
# onnx_yolo26_seg.py's CLASSES_TO_DETECT (keeps ByteTracker's class-agnostic IoU matching
# safe, keeps mask coloring keyed on track_id alone). Only class id 1 ("person") is
# confirmed against this specific export -- see PERSON_CLASS_ID comment below.
MODEL_FILENAME = 'rf-detr-seg-nano.onnx'

# This export's OUTPUT NAMES DO NOT MATCH THEIR OWN SHAPES:
#   name='pred_masks'  shape=[1, 100, 4]        <- this is actually the BOX tensor
#   name='pred_boxes'  shape=[1, 100, 91]       <- this is actually the CLASS LOGIT tensor
#   name='pred_logits' shape=[1, 100, 96, 96]   <- this is actually the MASK tensor
# on_model_loaded() below resolves each output's ACTUAL index by its shape signature
# (last dim 4 -> boxes, last dim matching NUM_CLASSES -> logits, 4D -> masks) once at
# load time instead of trusting the name strings or hardcoding positions 0/1/2, so this
# stays correct even if a future re-export reorders the graph outputs.
NUM_QUERIES = 100     # this model's query count (rf-detr-small.onnx, non-seg, uses 300)
NUM_CLASSES = 91      # standard COCO-91 (paper table with gaps) class-logit width

# Standard COCO-91 convention puts "person" at id 1; ONLY this id is verified against
# this specific export -- no other class index is mapped or supported by this
# person-only script.
PERSON_CLASS_ID = 1

# Model input is 384x384 (much smaller than YOLO26's 640x640) -- TD's fit_square_sm needs
# its Inputwidth par set to 384 to match, using 'fill' (stretch) resize same as this
# model's own training-time preprocessing (plain Image.resize(), no letterbox) -- boxes
# therefore map straight back to normalized 0-1 frame coords with no padding-offset math.
MODEL_INPUT_SIZE = 384

# ImageNet mean/std normalization (this model's own preprocessing, confirmed against the
# reference script) -- NOT just a /255 like YOLO. TD delivers numpyArray() already as
# float32 0-1, so this is applied directly without an extra /255 step.
_MEANS = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STDS = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def _sigmoid(x):
	return 1.0 / (1.0 + np.exp(-x))


# Confidence threshold for a detected person to be shown/tracked (0.0 - 1.0). ByteTracker's
# "high confidence" threshold -- detections at or above this score are matched first and
# can start brand-new tracks. Real detections score well above this; background noise
# stays well under it, so 0.5 leaves comfortable margin either side.
CONF_THRESHOLD = 0.5

# ByteTracker's "low confidence" threshold -- see onnx_yolo26_seg.py's identical comment
# for why this two-stage split exists (ByteTrack's actual innovation: recovering existing
# tracks through occlusion/motion blur without letting weak detections start new ones).
LOW_CONF_THRESHOLD = 0.2

# UNLIKE every other detector in this project, there is deliberately NO NMS threshold/pass
# here. RF-DETR (like every DETR-family model) is trained via Hungarian bipartite matching
# for one-prediction-per-object, so duplicate suppression is baked into training rather
# than needed as a postprocess step -- same reasoning as onnx_yunet.py's internal-NMS
# model, just architectural here instead of a library call.
MIN_BOX_WIDTH = 0.02
MIN_BOX_HEIGHT = 0.02

# Reject a decoded mask that fills less than this fraction of ITS OWN detection box (after
# cropping to that box -- see postprocess()) -- identical reasoning to
# onnx_yolo26_seg.py's MIN_MASK_AREA_RATIO (scale-invariant regardless of how near/far a
# person is). Real detections typically fill ~30-50% of their own box.
MIN_MASK_AREA_RATIO = 0.15

# Sigmoid probability cutoff used ONLY to compute the fill-ratio noise-rejection check --
# does NOT binarize the visual output (stays soft/continuous, see class docstring).
MASK_THRESHOLD = 0.5

# Whether to write per-frame tracking data to table_output at all -- see
# onnx_yolo26_seg.py's identical OUTPUT_TRACK_DATA comment.
OUTPUT_TRACK_DATA = True

# Tracker: max frames to keep a lost track alive.
TRACKER_MAX_AGE = 30

# Tracker: min IoU to accept a match between a track and a detection.
TRACKER_IOU_THRESHOLD = 0.3

# Tracker: total matched frames (not necessarily consecutive) a brand-new track needs
# before it's confirmed and shown/output at all.
TRACKER_MIN_HITS = 3

# Smoothing factor for box position/size lerp (0 = no smoothing, 1 = frozen). Masks are
# NOT smoothed pixel-wise -- a track's mask is simply held at its last real decoded value
# across lost/predicted-only frames, same as onnx_yolo26_seg.py.
OUTPUT_SMOOTHING = 0.5

# Draw masks/boxes on the output image?
DRAW_BOXES = False


# ==================== RF-DETR PEOPLE SEGMENTATION ====================

class RFDETRSegmentationInference(ONNXInferenceManager):
	"""RF-DETR (rf-detr-seg-small.onnx) instance segmentation, specialized for tracked
	PEOPLE segmentation -- a from-scratch sibling to onnx_yolo26_seg.py using the same
	ByteTracker-based lifecycle and native-resolution soft-matte output philosophy, but
	with a genuinely different model architecture underneath:

	- DETR-family set prediction: one prediction per object query (100 queries here), no
	  NMS pass at all (see MIN_BOX_WIDTH's comment block).
	- Multi-label sigmoid classification (not softmax + background class) -- score is
	  each query's max class probability, label is its argmax.
	- Masks are NOT decoded from shared prototypes + per-detection coefficients like
	  YOLO26-seg -- each query already carries its own full mask tensor directly
	  (100, 96, 96), and each 96x96 grid is FULL-FRAME-aligned (covers the whole input
	  frame at low res, not just that query's own box region). Same box-cropping
	  technique as YOLO26-seg's proto decode still applies (crop to the query's own box
	  in native 96x96 space, both for noise-rejection AND to keep the visual matte free
	  of stray activations from other people/background), it's just applied to an
	  already-decoded mask instead of a matmul'd one.
	- This export's OUTPUT NAMES DON'T MATCH THEIR SHAPES (see MODEL_FILENAME comment) --
	  on_model_loaded() resolves the real box/logit/mask output indices from their shapes
	  once at load time rather than trusting names or hardcoding positions.

	The matte is output at the mask tensor's NATIVE resolution (96x96), not upscaled in
	Python -- same reasoning as onnx_yolo26_seg.py: upscaling an already-decided soft field
	belongs downstream in TD's own GPU pipeline, and skipping a per-frame Python-side
	resize (unlike the reference script's per-mask PIL resize to full frame) is a real
	performance win specific to this model, on top of DETR's no-NMS savings.
	"""

	def __init__(self):
		super().__init__()
		# This script's inference is fast/consistent enough that the synchronous stall
		# from delayed=False costs less end-to-end latency than the staleness
		# delayed=True's async readback can introduce under load -- see Round 2 in
		# td-threaded-inference-optimization.md for the full investigation (and why this
		# is set per-script rather than changed as the base class default).
		self.numpy_array_delayed = False
		self.opOutputTableDAT = parent().op('table_output')
		self.conf_threshold = CONF_THRESHOLD
		self.low_conf_threshold = LOW_CONF_THRESHOLD
		self.tracker = ByteTracker(
			high_thresh=CONF_THRESHOLD, low_thresh=LOW_CONF_THRESHOLD,
			match_thresh=TRACKER_IOU_THRESHOLD, track_buffer=TRACKER_MAX_AGE,
			min_hits=TRACKER_MIN_HITS,
		)
		# Per-track box position/size smoothing state, keyed by track_id.
		self._box_state = {}
		# Per-track LAST KNOWN decoded mask (native-resolution soft float32 probability
		# array, box-cropped but NOT hard-thresholded), keyed by track_id -- held across
		# lost/predicted-only frames rather than smoothed or re-decoded.
		self._mask_state = {}
		# Mask tensor's native resolution -- set from the model's actual output shape on
		# first real inference; the 96x96 default matches this model's confirmed
		# architecture and is only ever used before that first frame lands.
		self._proto_h = 96
		self._proto_w = 96
		# Resolved output indices (see MODEL_FILENAME comment) -- set in on_model_loaded().
		self._boxes_idx = 0
		self._logits_idx = 1
		self._masks_idx = 2
		# Structured tracking data exposed for CHOP/table consumption
		self.tracked_objects = []
		# Pre-allocated buffers (lazily sized)
		self._output_buf = None
		self._output_buf_shape = None
		self._input_tensor_buf = None
		self._input_buf_shape = None

	def onSetupParameters(self, scriptOp):
		"""Add RF-DETR-Seg-specific parameters alongside base class params."""
		super().onSetupParameters(scriptOp)
		page = scriptOp.appendCustomPage('RFDETR-Seg')
		p = page.appendFloat('Confthreshold', label='Confidence Threshold', size=1)
		p[0].default = CONF_THRESHOLD
		p[0].min = 0.0
		p[0].max = 1.0
		p[0].clampMin = True
		p[0].clampMax = True
		p[0].help = object_tracker.par_help('Confthreshold', subject='person')
		scriptOp.par.Confthreshold = CONF_THRESHOLD
		p = page.appendFloat('Lowconfthreshold', label='Low Confidence Threshold (Recovery)', size=1)
		p[0].default = LOW_CONF_THRESHOLD
		p[0].min = 0.0
		p[0].max = 1.0
		p[0].clampMin = True
		p[0].clampMax = True
		p[0].help = object_tracker.par_help('Lowconfthreshold', subject='person')
		scriptOp.par.Lowconfthreshold = LOW_CONF_THRESHOLD
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
			"person is). Real detections typically fill ~30-50% of their own box; much lower "
			"usually means a degenerate/noisy mask.")
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
			"toggle: this is real per-frame CPU work that's entirely separate from the visual matte -- "
			"turn off if nothing downstream actually reads table_output.")
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
		"""Return path to the RF-DETR segmentation model."""
		model_dir = os.path.join(project.folder, 'data', 'ml', 'rf-detr')
		return os.path.join(model_dir, MODEL_FILENAME)

	def on_model_loaded(self, session):
		"""Log model I/O and resolve the REAL box/logit/mask output indices from their
		shapes -- this export's output NAMES don't match their own shapes (see
		MODEL_FILENAME comment), so name-based lookup would silently pick the wrong
		tensor. Falls back to the confirmed-live positions (0, 1, 2) only if the shape
		signatures don't resolve cleanly (e.g. a differently-shaped re-export)."""
		outputs = session.get_outputs()
		self.printONNX(f"RF-DETR-Seg model outputs ({len(outputs)}):")
		for i, o in enumerate(outputs):
			self.printONNX(f"  [{i}] name='{o.name}' shape={o.shape} type={o.type}")
		inputs = session.get_inputs()
		for i, inp in enumerate(inputs):
			self.printONNX(f"  input[{i}] name='{inp.name}' shape={inp.shape} type={inp.type}")
		self.check_providers(session)

		boxes_idx = logits_idx = masks_idx = None
		for i, o in enumerate(outputs):
			shape = [d if isinstance(d, int) else -1 for d in o.shape]
			if len(shape) == 3 and shape[-1] == 4:
				boxes_idx = i
			elif len(shape) == 3 and shape[-1] == NUM_CLASSES:
				logits_idx = i
			elif len(shape) == 4:
				masks_idx = i

		if boxes_idx is None or logits_idx is None or masks_idx is None:
			self.printONNX(
				f"WARNING: could not resolve boxes/logits/masks outputs by shape "
				f"(got boxes_idx={boxes_idx}, logits_idx={logits_idx}, masks_idx={masks_idx}) -- "
				"falling back to confirmed-live positions 0/1/2. Re-verify against this export."
			)
			boxes_idx = boxes_idx if boxes_idx is not None else 0
			logits_idx = logits_idx if logits_idx is not None else 1
			masks_idx = masks_idx if masks_idx is not None else 2

		self._boxes_idx = boxes_idx
		self._logits_idx = logits_idx
		self._masks_idx = masks_idx
		self.printONNX(
			f"Resolved by shape: boxes=outputs[{boxes_idx}], logits=outputs[{logits_idx}], "
			f"masks=outputs[{masks_idx}] (names are unreliable on this export -- see comment)"
		)

	def preprocess(self, nA):
		"""Preprocess input for RF-DETR. Assumes TD has already resized input to the
		model's expected 384x384 dimensions upstream (this network's fit_square_sm, using
		'fill'/stretch mode -- same as this model's own training-time preprocessing, no
		letterbox), same no-redundant-internal-resize assumption as
		onnx_yolo26_seg.py/onnx_yolo26_pose.py. UNLIKE those, this model needs ImageNet
		mean/std normalization on top of the flip+channel-order handling -- skipping it
		would silently wreck detection quality rather than error out."""
		self.original_h, self.original_w = nA.shape[:2]
		num_channels = nA.shape[2] if len(nA.shape) == 3 else 1

		needed = (1, 3, self.original_h, self.original_w)
		if self._input_buf_shape != needed:
			self._input_tensor_buf = np.empty(needed, dtype=np.float32)
			self._input_buf_shape = needed

		if num_channels >= 3:
			flipped = nA[::-1, :, :3]  # flip V + drop alpha (view, no alloc)
		else:
			img = self.npu.flip_v(nA)
			flipped = self.npu.grayscale_to_rgb(img)

		for c in range(3):
			self._input_tensor_buf[0, c] = (flipped[:, :, c] - _MEANS[c]) / _STDS[c]

		return self._input_tensor_buf

	def postprocess(self, outputs):
		"""Postprocess RF-DETR-Seg outputs -- see class docstring for the architectural
		differences from onnx_yolo26_seg.py this accounts for (set prediction/no NMS,
		sigmoid multi-label scoring, directly-provided per-query masks)."""
		if len(outputs) < 3:
			needed_shape = (self._proto_h, self._proto_w, 3)
			if self._output_buf is None or self._output_buf_shape != needed_shape:
				self._output_buf = np.zeros(needed_shape, dtype=np.float32)
				self._output_buf_shape = needed_shape
			return self.npu.flip_v(self._output_buf)

		boxes_raw = outputs[self._boxes_idx][0]    # (100, 4) cxcywh, normalized 0-1
		logits_raw = outputs[self._logits_idx][0]  # (100, 91)
		masks_raw = outputs[self._masks_idx][0]    # (100, 96, 96) raw logits, full-frame-aligned
		proto_h, proto_w = masks_raw.shape[1], masks_raw.shape[2]
		self._proto_h, self._proto_w = proto_h, proto_w

		probs = _sigmoid(logits_raw)
		scores = probs.max(axis=1)
		labels = probs.argmax(axis=1)

		# cxcywh -> xyxy, normalized (boxes are already relative to the 'fill'/stretch-
		# resized frame, matching TD's fit_square_sm -- no letterbox offset to undo).
		cx, cy, w, h = boxes_raw[:, 0], boxes_raw[:, 1], boxes_raw[:, 2], boxes_raw[:, 3]
		boxes_xyxy = np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], axis=-1)
		boxes_xyxy = np.clip(boxes_xyxy, 0.0, 1.0)

		# Read thresholds from custom parameters (updated each frame)
		self.conf_threshold = self._par_or_default('Confthreshold', CONF_THRESHOLD)
		self.low_conf_threshold = self._par_or_default('Lowconfthreshold', LOW_CONF_THRESHOLD)
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
		# split internally (see onnx_yolo26_seg.py's identical comment).
		valid = (labels == PERSON_CLASS_ID) & (scores > self.low_conf_threshold)
		valid &= (boxes_xyxy[:, 2] - boxes_xyxy[:, 0] >= min_box_width) & (boxes_xyxy[:, 3] - boxes_xyxy[:, 1] >= min_box_height)

		boxes_xyxy = boxes_xyxy[valid]
		scores = scores[valid]
		masks_raw = masks_raw[valid]

		# Keep a copy in the model's NATIVE (pre-TD-flip) orientation -- needed to crop
		# each mask to its own box region below, since masks_raw is in that same native
		# top-down orientation and never gets TD's Y-flip applied to it.
		boxes_native = boxes_xyxy.copy()

		# Flip Y-axis for TouchDesigner (model uses top-down, TD uses bottom-up)
		boxes_xyxy[:, 1], boxes_xyxy[:, 3] = 1.0 - boxes_xyxy[:, 3], 1.0 - boxes_xyxy[:, 1]

		# No NMS pass -- see MIN_BOX_WIDTH's comment block (DETR set prediction doesn't
		# produce the duplicate detections NMS exists to remove).

		detections = []
		if len(boxes_xyxy) > 0:
			masks = _sigmoid(masks_raw)
			binary_masks = masks > mask_threshold

			# Crop each mask to its own detection box -- these masks are FULL-FRAME-aligned
			# (see class docstring), same reasoning as onnx_yolo26_seg.py's proto-mask
			# crop: without confining it to the box that produced it, activations
			# elsewhere in the frame (background, another person) show through as noise.
			px1 = np.clip((boxes_native[:, 0] * proto_w).astype(np.intp), 0, proto_w)
			py1 = np.clip((boxes_native[:, 1] * proto_h).astype(np.intp), 0, proto_h)
			px2 = np.clip(np.ceil(boxes_native[:, 2] * proto_w).astype(np.intp), 0, proto_w)
			py2 = np.clip(np.ceil(boxes_native[:, 3] * proto_h).astype(np.intp), 0, proto_h)
			col_idx = np.arange(proto_w)
			row_idx = np.arange(proto_h)
			box_areas_px = np.maximum((px2 - px1) * (py2 - py1), 1)
			for i in range(len(binary_masks)):
				col_in_box = (col_idx >= px1[i]) & (col_idx < px2[i])
				row_in_box = (row_idx >= py1[i]) & (row_idx < py2[i])
				in_box = row_in_box[:, np.newaxis] & col_in_box[np.newaxis, :]
				binary_masks[i] &= in_box
				masks[i] *= in_box

			mask_areas = binary_masks.sum(axis=(1, 2))
			fill_ratios = mask_areas / box_areas_px

			for i in range(len(boxes_xyxy)):
				if fill_ratios[i] <= min_mask_area_ratio:
					continue
				detections.append({
					'box': boxes_xyxy[i].tolist(),
					'score': float(scores[i]),
					'class_id': PERSON_CLASS_ID,
					'class_name': 'person',
					# Soft (pre-threshold) probability, box-cropped -- see class docstring.
					'mask': masks[i],
					'mask_area_ratio': float(fill_ratios[i]),
				})

		# Update tracker (runs on main thread, no lock needed)
		active_tracks = self.tracker.update(detections)

		active_ids = {t.track_id for t in active_tracks}
		self.tracked_objects = []
		for t in active_tracks:
			if t.score < self.conf_threshold or not t.confirmed:
				continue
			box = t.box  # Kalman estimate
			smoothed = object_tracker.box_smooth(self._box_state, t.track_id, box, smoothing)

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
				'class_id': t.payload.get('class_id', PERSON_CLASS_ID),
				'class_name': t.payload.get('class_name', 'person'),
				'score': t.score,
				'cx': cx, 'cy': cy, 'w': w, 'h': h,
				'x_left': smoothed[0],
				'x_right': smoothed[2],
				'y_top': smoothed[3],
				'y_bottom': smoothed[1],
				'vx': float(t.mean[4]), 'vy': float(t.mean[5]),
				'lost_frames': t.lost_frames,
				'total_frames': t.total_frames,
				'mask_area_ratio': t.payload.get('mask_area_ratio', 0.0),
				'mask': held_mask,
			})

		object_tracker.prune_stale(active_ids, self._box_state, self._mask_state)

		output_img = self.npu.flip_v(self.draw_tracked_masks(draw_labels=DRAW_BOXES))
		return output_img

	def on_result_published(self):
		"""Flush table_output from tracked_objects right after this frame's texture
		publishes, before the next frame's capture/dispatch -- see
		ONNXInferenceManager.on_result_published()'s docstring. Gated by Outputtrackdata,
		same reasoning as onnx_yolo26_seg.py's identical method."""
		if self._par_or_default('Outputtrackdata', OUTPUT_TRACK_DATA):
			self.write_tracks_to_table()

	def draw_tracked_masks(self, draw_labels=False):
		"""Render a soft-edged white silhouette matte for currently (this-frame) detected
		people at the mask tensor's NATIVE resolution (96x96) -- see class docstring for
		why no upscaling happens here. Identical behavior/reasoning to
		onnx_yolo26_seg.py's method of the same name."""
		proto_h, proto_w = self._proto_h, self._proto_w
		composite = np.zeros((proto_h, proto_w), dtype=np.float32)
		for obj in self.tracked_objects:
			if obj['lost_frames'] > 0:
				continue
			mask = obj.get('mask')
			if mask is None:
				continue
			np.maximum(composite, mask, out=composite)

		composite = np.clip(composite, 0.0, 1.0)
		composite_rgb = np.repeat(composite[:, :, np.newaxis], 3, axis=2)

		if not draw_labels:
			return composite_rgb

		draw_img = cv2.cvtColor((composite_rgb * 255).astype(np.uint8), cv2.COLOR_RGB2BGR)

		def to_px(td_x, td_y):
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

		return cv2.cvtColor(draw_img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0

	# ==================== CHOP TRACKING OUTPUT ====================
	# To output tracking data to a CHOP, use a Script CHOP DAT with:
	#
	#   mgr = op('script1').module.inference_manager
	#   tracks = mgr.tracked_objects  # list of dicts
	#
	# Each dict contains: track_id, class_id, class_name, score,
	#   cx, cy, w, h, x_left, x_right, y_top, y_bottom, vx, vy (Kalman-estimated),
	#   lost_frames, total_frames, mask_area_ratio, mask (native-res bool array)
	#
	# For a Table DAT approach, call write_tracks_to_table() from a
	# Script DAT or Execute DAT each frame.

	def write_tracks_to_table(self):
		"""Helper to write current tracking data to a Table DAT -- identical schema to
		onnx_yolo26_seg.py's method of the same name (class_id/class_name are constant
		here, kept for schema parity across the project's seg-family scripts)."""
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
inference_manager = RFDETRSegmentationInference()
onnx_inference_manager.shutdown_and_register(parent().path, inference_manager)

# TouchDesigner callback wrappers that delegate to the manager
def onSetupParameters(scriptOp):
	return inference_manager.onSetupParameters(scriptOp)


def onPulse(par):
	return inference_manager.onPulse(par)


def onCook(scriptOp):
	inference_manager.onCook(scriptOp)

	global DRAW_BOXES
	DRAW_BOXES = parent().par.Drawdebug.eval() == 1

	# Table writes happen inside inference_manager.onCook(scriptOp) above now, via
	# on_result_published() (still gated by Outputtrackdata internally).


def onGetCookLevel(scriptOp: scriptCHOP) -> CookLevel:
	"""See onnx_yolo26_seg.py's identical method for why this is unconditionally ALWAYS
	rather than AUTOMATIC."""
	return CookLevel.ALWAYS
