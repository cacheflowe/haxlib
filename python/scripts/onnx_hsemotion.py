import os
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
# SCRFD-family face detector + HSEmotion facial-emotion classifier, ported from
# https://github.com/Shohruh72/Emotion_onnx/ to this project's shared
# ONNXInferenceManager + ByteTracker conventions.
DETECTOR_MODEL_FILENAME = 'detection.onnx'
EMOTION_MODEL_FILENAME = 'emotion.onnx'

# detection.onnx has 9 outputs (score_8, score_16, score_32, bbox_8, bbox_16, bbox_32,
# kps_8, kps_16, kps_32) -- matches the reference util.py's `len(outputs) == 9` branch:
# fmc=3, feat_stride_fpn=[8,16,32], num_anchors=2, use_kps=True. Keypoints are NOT
# decoded here -- the reference's own forward() never populates them either, and nothing
# downstream (emotion recognition) needs them.
FEAT_STRIDE_FPN = [8, 16, 32]
NUM_ANCHORS = 2

# Reference preprocessing: cv2.dnn.blobFromImage(x, 1.0/128, size, (127.5,127.5,127.5),
# swapRB=True), i.e. (BGR_0-255_pixel - 127.5) / 128, then BGR->RGB swap. TD delivers RGB
# 0-1 already, so this becomes (pixel*255 - 127.5) / 128 directly -- no channel swap
# needed since TD's channel order is already RGB.
_DET_MEAN = 127.5
_DET_SCALE = 1.0 / 128.0

# Emotion model's own normalization, from the reference HSEmotionRecognizer.preprocess()
# -- coincidentally identical to ImageNet's mean/std. img_size is 260, not the 224 that
# reference's own inline comment suggests; HSEmotionRecognizer hardcodes 260.
EMOTION_IMG_SIZE = 260
_EMO_MEANS = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_EMO_STDS = np.array([0.229, 0.224, 0.225], dtype=np.float32)

EMOTION_CLASSES = ['ANGER', 'DISGUST', 'FEAR', 'HAPPINESS', 'NEUTRAL', 'SADNESS', 'SURPRISE']

# Fixed ceiling for _classify_emotions_batch()'s padded batch size. ONNX Runtime's CUDA EP
# pays a one-time multi-second algorithm-search cost the first time it sees a given batch
# shape; since tracked-face count varies every frame, padding every call to this one fixed
# size keeps the shape constant so that cost is only paid once (see Round 5 in
# td-threaded-inference-optimization.md). Faces beyond this count in a single frame are
# simply not classified that frame (raise this if that's ever actually hit).
MAX_BATCH_FACES = 16

# Confidence threshold for a detected face to be shown/tracked. ByteTracker's "high
# confidence" threshold -- see onnx_yolo26_seg.py's identical comment for the two-stage
# high/low reasoning.
CONF_THRESHOLD = 0.5

# ByteTracker's "low confidence" recovery threshold.
LOW_CONF_THRESHOLD = 0.2

# IoU threshold for NMS on raw detections before tracking -- this detector, UNLIKE
# RF-DETR/YuNet, is a plain anchor-based FPN detector (not set-prediction, no baked-in
# NMS), so it genuinely needs this pass, same as onnx_yolo26_seg.py. 0.4 matches the
# reference FaceDetector's own nms_thresh default.
NMS_IOU_THRESHOLD = 0.4

MIN_BOX_WIDTH = 0.02
MIN_BOX_HEIGHT = 0.02

TRACKER_MAX_AGE = 30
TRACKER_IOU_THRESHOLD = 0.3
TRACKER_MIN_HITS = 3

# Smoothing factor for box position/size lerp AND emotion score lerp (0 = no smoothing,
# 1 = frozen) -- see class docstring for why emotion scores are smoothed the same way.
OUTPUT_SMOOTHING = 0.5

DRAW_BOXES = False

# How often (in frames) to actually re-run the emotion classifier, as a GLOBAL cadence
# shared by every currently-tracked face (not per-track) -- both because a single shared
# cadence is simpler to reason about, and because it's what makes batching (see
# _classify_emotions_batch()) possible at all: every face due for a fresh classification
# this frame gets folded into the SAME batched session.run() call. 1 = every frame (no
# throttle). Combined with Outputsmoothing's blend-lerp, a higher interval cuts
# classification cost roughly proportionally with little visible difference, since real
# facial expression doesn't change frame-to-frame at 60fps anyway.
EMOTION_INTERVAL = 3


# ==================== FACE + EMOTION TRACKING ====================

class HSEmotionInference(ONNXInferenceManager):
	"""SCRFD-family face detector + HSEmotion facial-emotion classifier
	(https://github.com/Shohruh72/Emotion_onnx/), adapted to this project's shared
	ONNXInferenceManager + ByteTracker pattern.

	Genuinely two-stage, unlike every other script in this project: face DETECTION runs
	through the normal threaded ONNXInferenceManager pipeline (session.run() on the
	persistent worker thread), but per-face EMOTION classification runs synchronously on
	the MAIN thread inside postprocess(), using a second plain (unthreaded)
	ort.InferenceSession. A single 260x260 classifier call is cheap enough that a full
	second threaded pipeline (its own queue/worker-thread machinery) isn't worth the
	added complexity, and this matches the reference demo's own unthreaded usage.

	Face crops for emotion classification come from the SAME resized working frame the
	detector runs on (see preprocess()'s self._last_frame_rgb) -- crop quality is bounded
	by this network's own Inputwidth, so increase that if emotion recognition needs
	sharper detail on distant/small faces.
	"""

	def __init__(self):
		super().__init__()
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
		# Per-track smoothed emotion scores (shape (7,)), keyed by track_id -- held/
		# blended across frames the same way box position is, so per-frame classifier
		# noise doesn't flicker the displayed dominant emotion.
		self._emotion_state = {}
		self.tracked_objects = []
		self._input_tensor_buf = None
		self._input_buf_shape = None
		self._output_buf = None
		self._output_buf_shape = None
		self.original_h = None
		self.original_w = None
		# Kept from preprocess() (main thread) for postprocess()'s face-crop step -- the
		# SAME resized RGB frame the detector runs on (see class docstring), a plain owned
		# numpy copy (NOT a view into TD's own buffer, which isn't safe to hold past the
		# frame it was captured in).
		self._last_frame_rgb = None
		# Second, unthreaded ONNX session for emotion classification -- loaded once
		# alongside the detector in on_model_loaded(). Called synchronously from
		# postprocess() (main thread), never from the worker thread.
		self._emotion_session = None
		# Global (not per-track) cadence counter for the emotion-classify throttle -- see
		# EMOTION_INTERVAL/Emotioninterval par help for why this is shared across all
		# tracked faces rather than staggered per-track (it's what makes batching all of
		# them into one session.run() call possible).
		self._emotion_frame_counter = 0

	def onSetupParameters(self, scriptOp):
		"""Add HSEmotion-specific parameters alongside base class params."""
		super().onSetupParameters(scriptOp)
		page = scriptOp.appendCustomPage('HSEmotion')
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
		p = page.appendToggle('Outputtrackdata', label='Output Track Data (Table)')
		p[0].default = True
		p[0].help = ("Whether to write per-frame face tracking + emotion data to table_output at "
			"all. Pure performance toggle: real per-frame CPU work (formatting every column for "
			"every confirmed face) that's separate from the visual debug output -- turn off if "
			"nothing downstream actually reads table_output.")
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
		p = page.appendFloat('Outputsmoothing', label='Output Smoothing (Box + Emotion)', size=1)
		p[0].default = OUTPUT_SMOOTHING
		p[0].min = 0.0
		p[0].max = 1.0
		p[0].clampMin = True
		p[0].clampMax = True
		p[0].help = object_tracker.par_help('Outputsmoothing', extra=(
			"Also smooths each tracked face's emotion scores frame to frame (same value, same "
			"lerp), so single-frame classifier noise doesn't flicker the displayed emotion label."
		))
		scriptOp.par.Outputsmoothing = OUTPUT_SMOOTHING
		p = page.appendFloat('Emotioninterval', label='Emotion Classify Interval (Frames)', size=1)
		p[0].default = EMOTION_INTERVAL
		p[0].min = 1.0
		p[0].max = 30.0
		p[0].clampMin = True
		p[0].clampMax = False
		p[0].help = ("How often (in frames) to actually re-run the emotion classifier, shared by "
			"every currently-tracked face at once (1 = every frame, no throttle). All faces due "
			"for classification on a given frame are batched into a single call rather than one "
			"call per face, so this directly controls both how often AND how efficiently emotion "
			"gets classified. Between classification frames, each face's last (Outputsmoothing-"
			"blended) emotion reading is held -- real facial expression doesn't change frame to "
			"frame at 60fps, so a modest interval (e.g. 3-5) is usually visually indistinguishable "
			"from classifying every single frame, at a fraction of the cost.")
		scriptOp.par.Emotioninterval = EMOTION_INTERVAL
		p = page.appendToggle('Drawdebug', label='Draw Debug Overlay')
		p[0].default = DRAW_BOXES
		p[0].help = ("Draws face box outlines + track id + dominant emotion label on the output "
			"image. This IS the visual product for a face/emotion script (unlike the seg-family "
			"scripts, there's no dense mask to fall back on) -- turn off only if you just want "
			"table_output's data and a blank image.")
		scriptOp.par.Drawdebug = DRAW_BOXES

	def get_model_path(self):
		"""Return path to the SCRFD face detector model."""
		model_dir = os.path.join(project.folder, 'data', 'ml', 'hsemotion')
		return os.path.join(model_dir, DETECTOR_MODEL_FILENAME)

	def on_model_loaded(self, session):
		"""Log detector I/O, warn if the export doesn't match the confirmed 9-output
		layout, and load the second (unthreaded) emotion classifier session."""
		outputs = session.get_outputs()
		self.printONNX(f"HSEmotion face detector outputs ({len(outputs)}):")
		for o in outputs:
			self.printONNX(f"  name='{o.name}' shape={o.shape} type={o.type}")
		inputs = session.get_inputs()
		for inp in inputs:
			self.printONNX(f"  input name='{inp.name}' shape={inp.shape} type={inp.type}")
		self.check_providers(session)
		if len(outputs) != 9:
			self.printONNX(
				f"WARNING: expected 9 outputs (score/bbox/kps x 3 FPN strides), got "
				f"{len(outputs)} -- postprocess() assumes the confirmed-live SCRFD 9-output "
				"layout (fmc=3, feat_stride_fpn=[8,16,32], num_anchors=2)."
			)

		emotion_path = os.path.join(project.folder, 'data', 'ml', 'hsemotion', EMOTION_MODEL_FILENAME)
		self._emotion_session = ort.InferenceSession(emotion_path, providers=onnx_inference_manager.providers())
		self.printONNX(f"Emotion classifier loaded: {emotion_path}")
		self.printONNX(f"  Active providers: {self._emotion_session.get_providers()}")

	def preprocess(self, nA):
		"""Preprocess for the SCRFD face detector. UNLIKE the fixed-square-input detectors
		elsewhere in this project (BlazeFace/BlazePalm/YOLO26), SCRFD's ONNX graph declares
		a fully dynamic input shape (['?', 3, '?', '?']) -- a fully-convolutional FPN
		detector trained on WIDER FACE images at their native aspect ratio, not squished
		to square. So this network intentionally resizes upstream WITHOUT forcing a
		square shape (whatever fit/resolution TOP is wired above this script), and both
		preprocess() and the per-stride anchor decode below work in separate
		self.original_h/self.original_w terms rather than assuming square input."""
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

		# Kept for postprocess()'s per-face crop step -- see class docstring. A real copy
		# (not a view), since nA/flipped are TD-owned buffers not safe to hold past this call.
		self._last_frame_rgb = np.ascontiguousarray(flipped, dtype=np.float32)

		for c in range(3):
			self._input_tensor_buf[0, c] = (flipped[:, :, c] * 255.0 - _DET_MEAN) * _DET_SCALE

		return self._input_tensor_buf

	def postprocess(self, outputs):
		"""Decode SCRFD detections, track faces, classify emotion per tracked face."""
		if len(outputs) != 9:
			needed_shape = (self.original_h or 640, self.original_w or 640, 3)
			if self._output_buf is None or self._output_buf_shape != needed_shape:
				self._output_buf = np.zeros(needed_shape, dtype=np.float32)
				self._output_buf_shape = needed_shape
			return self.npu.flip_v(self._output_buf)

		input_h, input_w = self.original_h, self.original_w

		self.conf_threshold = self._par_or_default('Confthreshold', CONF_THRESHOLD)
		self.low_conf_threshold = self._par_or_default('Lowconfthreshold', LOW_CONF_THRESHOLD)
		nms_iou_threshold = self._par_or_default('Nmsiouthreshold', NMS_IOU_THRESHOLD)
		min_box_width = self._par_or_default('Minboxwidth', MIN_BOX_WIDTH)
		min_box_height = self._par_or_default('Minboxheight', MIN_BOX_HEIGHT)
		self.tracker.high_thresh = self.conf_threshold
		self.tracker.low_thresh = self.low_conf_threshold
		self.tracker.match_thresh = self._par_or_default('Trackiouthreshold', TRACKER_IOU_THRESHOLD)
		self.tracker.track_buffer = self._par_or_default('Tracklossframes', TRACKER_MAX_AGE)
		self.tracker.min_hits = int(self._par_or_default('Trackconfirmframes', TRACKER_MIN_HITS))
		smoothing = self._par_or_default('Outputsmoothing', OUTPUT_SMOOTHING)

		# Decode each FPN stride's score/bbox heads against its own anchor grid -- see
		# class docstring / FEAT_STRIDE_FPN comment for the confirmed 9-output layout.
		# Keep everything down to the LOW threshold -- ByteTracker does its own high/low
		# split internally (see onnx_yolo26_seg.py's identical comment).
		scores_list = []
		bboxes_list = []
		for idx, stride in enumerate(FEAT_STRIDE_FPN):
			scores = outputs[idx][0, :, 0]              # score_{stride}, (N,)
			boxes_raw = outputs[idx + 3][0] * stride     # bbox_{stride}, (N,4) distances

			height = input_h // stride
			width = input_w // stride
			grid = np.mgrid[:height, :width][::-1]  # (2, h, w) -> (x, y)
			anchor_centers = np.stack(grid, axis=-1).astype(np.float32).reshape(-1, 2)
			anchor_centers = anchor_centers * stride
			if NUM_ANCHORS > 1:
				anchor_centers = np.repeat(anchor_centers, NUM_ANCHORS, axis=0)

			pos_indices = np.where(scores >= self.low_conf_threshold)[0]
			if len(pos_indices) == 0:
				continue
			centers = anchor_centers[pos_indices]
			dist = boxes_raw[pos_indices]
			x1 = centers[:, 0] - dist[:, 0]
			y1 = centers[:, 1] - dist[:, 1]
			x2 = centers[:, 0] + dist[:, 2]
			y2 = centers[:, 1] + dist[:, 3]
			bboxes_list.append(np.stack([x1, y1, x2, y2], axis=-1))
			scores_list.append(scores[pos_indices])

		detections = []
		if scores_list:
			all_scores = np.concatenate(scores_list)
			all_boxes = np.concatenate(bboxes_list, axis=0)

			# Normalize to 0-1, native top-down orientation (pre-TD-flip) -- decoded in
			# pixel space of the 'fill'-stretched input_w x input_h frame.
			boxes_norm = all_boxes / np.array([input_w, input_h, input_w, input_h], dtype=np.float32)
			boxes_norm = np.clip(boxes_norm, 0.0, 1.0)

			valid = (boxes_norm[:, 2] - boxes_norm[:, 0] >= min_box_width) & (boxes_norm[:, 3] - boxes_norm[:, 1] >= min_box_height)
			boxes_native = boxes_norm[valid]
			all_scores = all_scores[valid]

			# Collapse near-duplicate raw detections before tracking -- this detector,
			# unlike RF-DETR/YuNet, has no NMS baked into its own graph (plain anchor-
			# based FPN head), so it genuinely needs this pass.
			if len(boxes_native) > 0:
				keep = _nms(boxes_native, all_scores, nms_iou_threshold)
				boxes_native = boxes_native[keep]
				all_scores = all_scores[keep]

			# Flip Y-axis for TouchDesigner (model uses top-down, TD uses bottom-up)
			boxes_td = boxes_native.copy()
			boxes_td[:, 1], boxes_td[:, 3] = 1.0 - boxes_td[:, 3], 1.0 - boxes_td[:, 1]

			for i in range(len(boxes_td)):
				detections.append({
					'box': boxes_td[i].tolist(),
					'score': float(all_scores[i]),
					# native (pre-flip) box kept alongside for the emotion-crop step below
					'box_native': boxes_native[i].tolist(),
				})

		# Update tracker (runs on main thread, no lock needed)
		active_tracks = self.tracker.update(detections)

		# Pass 1: box smoothing + collect each confirmed track's native-space box, but
		# DON'T classify emotion yet -- collected first so every face due for
		# classification this frame can be folded into ONE batched call below instead of
		# one call per face (see _classify_emotions_batch()).
		confirmed = []
		for t in active_tracks:
			if t.score < self.conf_threshold or not t.confirmed:
				continue
			box = t.box  # Kalman estimate (TD-flipped orientation)
			smoothed = object_tracker.box_smooth(self._box_state, t.track_id, box, smoothing)

			box_native = t.payload.get('box_native')
			if box_native is None:
				# A lost-but-still-confirmed track (Kalman-predicted only, no fresh
				# detection this frame) has no fresh box_native in its payload -- flip
				# the smoothed TD-space box back to native instead of skipping
				# classification entirely, so a briefly-occluded face still gets a
				# (slightly stale, held) emotion reading rather than none at all.
				x1, y1_td, x2, y2_td = smoothed
				box_native = [x1, 1.0 - y2_td, x2, 1.0 - y1_td]
			confirmed.append({'track': t, 'smoothed': smoothed, 'box_native': box_native})

		# Emotion classification -- synchronous, main thread, batched across every
		# confirmed face at once (see class docstring), throttled to once every
		# Emotioninterval frames (a GLOBAL cadence, not per-track -- see Emotioninterval
		# par help for why). Between classification frames, each face's last
		# (Outputsmoothing-blended) reading is simply held as-is.
		emotion_interval = max(1, int(self._par_or_default('Emotioninterval', EMOTION_INTERVAL)))
		self._emotion_frame_counter += 1
		if confirmed and self._emotion_frame_counter % emotion_interval == 0:
			batch_results = self._classify_emotions_batch([c['box_native'] for c in confirmed])
			for c, emotion_scores in zip(confirmed, batch_results):
				if emotion_scores is None:
					continue
				track_id = c['track'].track_id
				prev = self._emotion_state.get(track_id)
				self._emotion_state[track_id] = (
					emotion_scores if prev is None
					else prev * smoothing + emotion_scores * (1.0 - smoothing)
				)

		self.tracked_objects = []
		for c in confirmed:
			t = c['track']
			smoothed = c['smoothed']
			held_emotion = self._emotion_state.get(t.track_id)

			cx = (smoothed[0] + smoothed[2]) / 2
			cy = (smoothed[1] + smoothed[3]) / 2
			w = smoothed[2] - smoothed[0]
			h = smoothed[3] - smoothed[1]
			emotion_label = EMOTION_CLASSES[int(np.argmax(held_emotion))] if held_emotion is not None else ''
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
				'emotion_label': emotion_label,
				'emotion_scores': held_emotion,
			})

		active_ids = {t.track_id for t in active_tracks}

		# Prune box/emotion state for tracks the tracker has dropped entirely.
		object_tracker.prune_stale(active_ids, self._box_state, self._emotion_state)

		if DRAW_BOXES:
			output_img = self.npu.flip_v(self.draw_tracked_faces())
		else:
			# Black frame -- no need to allocate/draw/flip/color-convert every frame when
			# the overlay is off, just reuse a static cached buffer (same pattern as the
			# no-detector-output-yet branch above, and every other onnx_*.py script's
			# Drawdebug handling).
			needed_shape = (self.original_h or 640, self.original_w or 640, 3)
			if self._output_buf is None or self._output_buf_shape != needed_shape:
				self._output_buf = np.zeros(needed_shape, dtype=np.float32)
				self._output_buf_shape = needed_shape
			output_img = self._output_buf
		return output_img

	def on_result_published(self):
		"""Flush table_output from tracked_objects right after this frame's texture
		publishes, before the next frame's capture/dispatch -- see
		ONNXInferenceManager.on_result_published()'s docstring. Gated by Outputtrackdata,
		same reasoning as onnx_yolo26_seg.py's identical method."""
		if self._par_or_default('Outputtrackdata', True):
			self.write_tracks_to_table()

	def _classify_emotions_batch(self, boxes_native):
		"""Crop every given face (native/pre-flip box, normalized 0-1) from the working
		frame (self._last_frame_rgb, the same one the detector ran on), resize each to
		260x260, and run them all through the emotion classifier in a SINGLE batched
		session.run() call rather than one call per face -- the emotion model's own input
		shape ([batch_size, 3, 260, 260]) supports this directly, matching the reference
		implementation's own predict_multi_emotions(). Batch size must stay fixed at
		MAX_BATCH_FACES across calls -- see Round 5 in
		td-threaded-inference-optimization.md for why a varying batch size is much worse
		than batching at all.

		Returns a list the same length as boxes_native, each element either a (7,)
		softmax score array or None for a degenerate/zero-size crop."""
		results = [None] * len(boxes_native)
		frame = self._last_frame_rgb
		if frame is None or self._emotion_session is None or not boxes_native:
			return results

		if len(boxes_native) > MAX_BATCH_FACES:
			self.printONNX(
				f"WARNING: {len(boxes_native)} faces this frame exceeds MAX_BATCH_FACES="
				f"{MAX_BATCH_FACES} -- classifying only the first {MAX_BATCH_FACES}. "
				"Raise MAX_BATCH_FACES if this is expected to happen regularly."
			)

		h, w = frame.shape[:2]
		chws = []
		valid_indices = []
		for i, box_native in enumerate(boxes_native[:MAX_BATCH_FACES]):
			x1 = int(np.clip(box_native[0] * w, 0, w - 1))
			y1 = int(np.clip(box_native[1] * h, 0, h - 1))
			x2 = int(np.clip(box_native[2] * w, x1 + 1, w))
			y2 = int(np.clip(box_native[3] * h, y1 + 1, h))
			crop = frame[y1:y2, x1:x2]
			if crop.size == 0:
				continue
			resized = cv2.resize(crop, (EMOTION_IMG_SIZE, EMOTION_IMG_SIZE))
			normed = (resized - _EMO_MEANS) / _EMO_STDS
			chws.append(normed.transpose(2, 0, 1).astype(np.float32))
			valid_indices.append(i)

		if not chws:
			return results

		# Pad to the FIXED MAX_BATCH_FACES shape (see MAX_BATCH_FACES comment) -- zero
		# frames are harmless, their outputs are simply never read back (only the first
		# len(chws) results are used below).
		num_real = len(chws)
		pad_count = MAX_BATCH_FACES - num_real
		if pad_count > 0:
			chws.extend([np.zeros((3, EMOTION_IMG_SIZE, EMOTION_IMG_SIZE), dtype=np.float32)] * pad_count)

		batch = np.stack(chws, axis=0)  # (MAX_BATCH_FACES, 3, 260, 260), constant shape
		logits = self._emotion_session.run(None, {'input': batch})[0]  # (MAX_BATCH_FACES, 7)
		logits = logits[:num_real]
		e_x = np.exp(logits - np.max(logits, axis=1, keepdims=True))
		softmax = e_x / e_x.sum(axis=1, keepdims=True)
		for out_i, orig_i in enumerate(valid_indices):
			results[orig_i] = softmax[out_i].astype(np.float32)
		return results

	def draw_tracked_faces(self):
		"""Render a debug view at the detector's native working resolution -- box
		outlines + track id + dominant emotion label. Optional overlay gated entirely
		behind the Drawdebug par at the postprocess() call site (skipped, not just drawn
		empty, when off -- see that call site's comment); this method itself always
		draws when called."""
		proto_h, proto_w = self.original_h or 640, self.original_w or 640
		draw_img = np.zeros((proto_h, proto_w, 3), dtype=np.uint8)

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

			cv2.rectangle(draw_img, (px1, py_top), (px2, py_bottom), color_bgr, 2)
			label = f"#{obj['track_id']} {obj['emotion_label']}"
			cv2.putText(draw_img, label, (px1, max(py_top - 6, 12)),
				cv2.FONT_HERSHEY_SIMPLEX, 0.5, color_bgr, 1, cv2.LINE_AA)

		return cv2.cvtColor(draw_img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0

	# ==================== CHOP TRACKING OUTPUT ====================
	# To output tracking data to a CHOP, use a Script CHOP DAT with:
	#
	#   mgr = op('script1').module.inference_manager
	#   tracks = mgr.tracked_objects  # list of dicts
	#
	# Each dict contains: track_id, score, cx, cy, w, h, x_left, x_right, y_top,
	#   y_bottom, vx, vy (Kalman-estimated), lost_frames, total_frames, emotion_label,
	#   emotion_scores (shape (7,) array in EMOTION_CLASSES order, or None)
	#
	# For a Table DAT approach, call write_tracks_to_table() from a
	# Script DAT or Execute DAT each frame.

	def write_tracks_to_table(self):
		"""Helper to write current face tracking + emotion data to a Table DAT."""
		tbl = self.opOutputTableDAT
		if tbl is None:
			return

		tbl.clear()
		header = [
			*object_tracker.label_header(),
			*object_tracker.box_header(),
			'emotion_label',
		]
		header += [f'emotion_{name.lower()}' for name in EMOTION_CLASSES]
		header += object_tracker.color_header()
		tbl.appendRow(header)
		for obj in self.tracked_objects:
			scores = obj['emotion_scores']
			score_strs = [f"{s:.4f}" for s in scores] if scores is not None else [''] * len(EMOTION_CLASSES)
			# Override: this track's emotion label instead of the default score%.
			row = [
				*object_tracker.label_row(
					obj['track_id'], obj['score'],
					label_text=f"{obj['track_id']} {obj['emotion_label']}",
				),
				*object_tracker.box_row(obj),
				obj['emotion_label'],
			]
			row += score_strs
			row += object_tracker.color_row(obj['track_id'])
			tbl.appendRow(row)


# Create global instance -- shut down any PREVIOUS instance first (releases its
# GPU-resident ONNX Runtime session(s) and stops its worker thread) so a script
# reload during active development doesn't leak both -- see
# onnx_inference_manager.shutdown_and_register()'s docstring for the full
# mechanism this avoids (and why it's NOT TD's own store()/fetch(), which risked
# a real crash trying to persist a live, unpicklable manager instance).
inference_manager = HSEmotionInference()
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
