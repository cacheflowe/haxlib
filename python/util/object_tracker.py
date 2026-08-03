"""
Generic ByteTrack-style multi-object tracker, shared across this project's ONNX
inference scripts (onnx_yolo26_pose.py, onnx_yolo26_obj_det.py, and future ones).

Reimplemented from the published ByteTrack method (Zhang et al., "ByteTrack: Multi-Object
Tracking by Associating Every Detection Box", ECCV 2022; reference implementation at
https://github.com/ifzhang/ByteTrack, MIT licensed) using only numpy -- this is an original
implementation of the published algorithm, not a copy of that or any other codebase, chosen
specifically so it runs unmodified in TouchDesigner's embedded Python (no scipy/lap/
cython_bbox available there).

Core idea vs. a plain greedy-IoU tracker (this project's old SimpleTracker):
  1. A Kalman filter (constant-velocity box model) predicts each track's position every
     frame, instead of a hand-rolled velocity EMA -- better motion prediction through
     brief occlusion/misses.
  2. Matching is solved as an optimal assignment (Hungarian algorithm) over the full
     cost matrix, instead of greedily grabbing the single best IoU pair each round --
     avoids suboptimal matches in crowded scenes where greedy picks can lock in a
     mediocre pairing early and starve a better one later.
  3. Two-stage association: detections are split into high/low confidence. High-confidence
     detections are matched first; then *low-confidence* detections (which most trackers
     discard as noise) are used to recover tracks still unmatched after stage 1 -- this
     is ByteTrack's actual innovation, and directly targets occluded/blurry/edge-case
     people that a confidence-thresholded detector alone tends to drop.

Usage (see onnx_yolo26_pose.py / onnx_yolo26_obj_det.py for real call sites):

    from object_tracker import ByteTracker

    tracker = ByteTracker(high_thresh=0.5, low_thresh=0.1, match_thresh=0.7, track_buffer=30)
    ...
    detections = [{'box': [x1, y1, x2, y2], 'score': 0.9, 'keypoints': [...]}, ...]
    tracks = tracker.update(detections)
    for t in tracks:
        t.track_id, t.box, t.score, t.lost_frames, t.total_frames
        t.confirmed              # False until matched min_hits total frames while alive (noise filter)
        t.payload['keypoints']   # whatever extra keys the detection carried, passed through

Boxes are [x1, y1, x2, y2] in whatever coordinate space the caller uses consistently
(this project uses normalized 0-1, TD bottom-up Y) -- the tracker itself is agnostic to
units, it only needs a consistent space to compute IoU and velocity in.

Also home to par_help() (see bottom of file) -- shared Par.help text for the common set of
tracker-related custom pars every script here exposes, so the explanations only live in one
place instead of being copy-pasted per script.
"""

import numpy as np


# ==================== BOX <-> KALMAN STATE CONVERSION ====================
# Kalman state is [cx, cy, aspect_ratio(w/h), h, vcx, vcy, vaspect, vh] -- the standard
# SORT/DeepSORT/ByteTrack state representation.

def _xyxy_to_xyah(box):
	x1, y1, x2, y2 = box
	w = max(x2 - x1, 1e-6)
	h = max(y2 - y1, 1e-6)
	cx = x1 + w / 2.0
	cy = y1 + h / 2.0
	return np.array([cx, cy, w / h, h], dtype=float)


def _xyah_to_xyxy(xyah):
	cx, cy, a, h = xyah
	w = a * h
	return [cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0]


# ==================== KALMAN FILTER (constant-velocity box model) ====================

class KalmanBoxFilter:
	"""8-state Kalman filter for a bounding box: position [cx, cy, a, h] plus their
	velocities. Pure numpy -- no scipy/filterpy required."""

	def __init__(self):
		ndim, dt = 4, 1.0
		self._motion_mat = np.eye(2 * ndim)
		for i in range(ndim):
			self._motion_mat[i, ndim + i] = dt
		self._update_mat = np.eye(ndim, 2 * ndim)
		# Noise scales relative to the box's own height, same convention as ByteTrack/DeepSORT.
		self._std_weight_position = 1.0 / 20
		self._std_weight_velocity = 1.0 / 160

	def initiate(self, measurement):
		mean = np.r_[measurement, np.zeros(4)]
		std = [
			2 * self._std_weight_position * measurement[3], 2 * self._std_weight_position * measurement[3],
			1e-2, 2 * self._std_weight_position * measurement[3],
			10 * self._std_weight_velocity * measurement[3], 10 * self._std_weight_velocity * measurement[3],
			1e-5, 10 * self._std_weight_velocity * measurement[3],
		]
		covariance = np.diag(np.square(std))
		return mean, covariance

	def predict(self, mean, covariance):
		std_pos = [
			self._std_weight_position * mean[3], self._std_weight_position * mean[3],
			1e-2, self._std_weight_position * mean[3],
		]
		std_vel = [
			self._std_weight_velocity * mean[3], self._std_weight_velocity * mean[3],
			1e-5, self._std_weight_velocity * mean[3],
		]
		motion_cov = np.diag(np.square(np.r_[std_pos, std_vel]))
		mean = self._motion_mat @ mean
		covariance = self._motion_mat @ covariance @ self._motion_mat.T + motion_cov
		return mean, covariance

	def _project(self, mean, covariance):
		std = [
			self._std_weight_position * mean[3], self._std_weight_position * mean[3],
			1e-1, self._std_weight_position * mean[3],
		]
		innovation_cov = np.diag(np.square(std))
		proj_mean = self._update_mat @ mean
		proj_cov = self._update_mat @ covariance @ self._update_mat.T + innovation_cov
		return proj_mean, proj_cov

	def update(self, mean, covariance, measurement):
		projected_mean, projected_cov = self._project(mean, covariance)
		chol_factor = np.linalg.cholesky(projected_cov)
		kalman_gain = np.linalg.solve(
			chol_factor.T, np.linalg.solve(chol_factor, (covariance @ self._update_mat.T).T)
		).T
		innovation = measurement - projected_mean
		new_mean = mean + innovation @ kalman_gain.T
		new_covariance = covariance - kalman_gain @ projected_cov @ kalman_gain.T
		return new_mean, new_covariance


# ==================== OPTIMAL ASSIGNMENT (Hungarian algorithm, pure numpy/python) ====================
# Classic O(n^3) "shortest augmenting path with potentials" formulation of the assignment
# problem (the standard textbook algorithm scipy.optimize.linear_sum_assignment also solves) --
# reimplemented directly from the well-known method description, not derived from any
# specific library's source. Verified against scipy across thousands of random matrices
# (square, rectangular, with a cost threshold) before being wired into ByteTracker.

def _hungarian_square(cost):
	"""cost: square (n, n) numpy array. Returns (row_ind, col_ind), a full assignment
	minimizing the total cost, both arrays 0..n-1 and in row order."""
	n = cost.shape[0]
	INF = float('inf')
	u = [0.0] * (n + 1)
	v = [0.0] * (n + 1)
	p = [0] * (n + 1)     # p[j] = row currently assigned to column j (1-indexed), 0 = none
	way = [0] * (n + 1)
	for i in range(1, n + 1):
		p[0] = i
		j0 = 0
		minv = [INF] * (n + 1)
		used = [False] * (n + 1)
		while True:
			used[j0] = True
			i0 = p[j0]
			delta = INF
			j1 = -1
			for j in range(1, n + 1):
				if not used[j]:
					cur = cost[i0 - 1, j - 1] - u[i0] - v[j]
					if cur < minv[j]:
						minv[j] = cur
						way[j] = j0
					if minv[j] < delta:
						delta = minv[j]
						j1 = j
			for j in range(n + 1):
				if used[j]:
					u[p[j]] += delta
					v[j] -= delta
				else:
					minv[j] -= delta
			j0 = j1
			if p[j0] == 0:
				break
		while j0:
			j1 = way[j0]
			p[j0] = p[j1]
			j0 = j1
	row_ind = np.zeros(n, dtype=int)
	col_ind = np.zeros(n, dtype=int)
	for j in range(1, n + 1):
		if p[j] != 0:
			row_ind[p[j] - 1] = p[j] - 1
			col_ind[p[j] - 1] = j - 1
	return row_ind, col_ind


def linear_sum_assignment_thresh(cost, thresh):
	"""Rectangular linear sum assignment with a max-cost cutoff: pairs costing more than
	`thresh` are dropped from the result (treated as not worth matching at all), same
	intent as ByteTrack's IoU-distance gating. Returns (row_ind, col_ind) of ACCEPTED
	matches only (may be shorter than min(rows, cols)).

	Naively minimizing total cost over a square-padded matrix does NOT in general maximize
	the count of accepted (<=thresh) matches -- a lower-count assignment can have lower raw
	total cost. Fixed by capping every above-threshold entry to one flat "reject" value
	strictly worse than the padding cost, and every at-or-below-threshold entry keeps its
	real cost, which is always strictly better than padding. That makes "minimize total
	cost" and "maximize accepted matches, then minimize their cost" the same objective:
	every swap of a pad for an eligible real pair strictly lowers cost, so the optimizer is
	always incentivized to use as many eligible pairs as a valid matching allows, and among
	assignments of that same maximum count it still finds the true minimum-cost one.
	Verified against brute-force search across randomized rectangular cases."""
	rows, cols = cost.shape
	if rows == 0 or cols == 0:
		return np.array([], dtype=int), np.array([], dtype=int)
	n = max(rows, cols)
	reject_cost = thresh + 1.0
	pad_cost = thresh + 0.5
	capped = np.where(cost <= thresh, cost, reject_cost)
	square = np.full((n, n), pad_cost, dtype=float)
	square[:rows, :cols] = capped
	row_ind, col_ind = _hungarian_square(square)
	keep = (row_ind < rows) & (col_ind < cols) & (square[row_ind, col_ind] <= thresh)
	return row_ind[keep], col_ind[keep]


# ==================== IoU ====================

def _iou_matrix(boxes_a, boxes_b):
	"""boxes_a: (A, 4), boxes_b: (B, 4), both [x1,y1,x2,y2]. Returns (A, B) IoU matrix."""
	a = boxes_a[:, np.newaxis, :]
	b = boxes_b[np.newaxis, :, :]
	x1 = np.maximum(a[..., 0], b[..., 0])
	y1 = np.maximum(a[..., 1], b[..., 1])
	x2 = np.minimum(a[..., 2], b[..., 2])
	y2 = np.minimum(a[..., 3], b[..., 3])
	inter = np.maximum(0, x2 - x1) * np.maximum(0, y2 - y1)
	area_a = (boxes_a[:, 2] - boxes_a[:, 0]) * (boxes_a[:, 3] - boxes_a[:, 1])
	area_b = (boxes_b[:, 2] - boxes_b[:, 0]) * (boxes_b[:, 3] - boxes_b[:, 1])
	union = area_a[:, np.newaxis] + area_b[np.newaxis, :] - inter
	return np.where(union > 0, inter / union, 0.0)


def nms(boxes, scores, iou_threshold):
	"""Greedy IoU-based NMS, shared across every ONNX script in this project rather than
	each re-implementing it. boxes: (N, 4) xyxy, scores: (N,). Returns indices to keep,
	highest score first. Collapsing near-duplicate raw detections BEFORE tracking matters
	regardless of the model: ByteTracker's matching is strictly 1:1 per frame, so a
	near-duplicate detection that doesn't win the match against the real track becomes a
	brand-new phantom track instead of just being dropped."""
	if len(boxes) == 0:
		return []
	order = scores.argsort()[::-1]
	keep = []
	while len(order) > 0:
		i = order[0]
		keep.append(i)
		if len(order) == 1:
			break
		rest = order[1:]
		ious = _iou_matrix(boxes[i:i + 1], boxes[rest])[0]
		order = rest[ious < iou_threshold]
	return keep


# ==================== TRACK ====================

class Track:
	"""One tracked object: a Kalman-filtered box plus an arbitrary payload dict carrying
	whatever model-specific extra data (keypoints, class_id, mask, ...) came with its most
	recent matched detection. The tracker itself never looks inside payload."""

	_next_id = 1
	_kf = KalmanBoxFilter()

	def __init__(self, box, score, payload, min_hits=1, freeze_velocity_on_loss=False):
		self.track_id = Track._next_id
		Track._next_id += 1
		self.mean, self.covariance = Track._kf.initiate(_xyxy_to_xyah(box))
		self.score = score
		self.payload = payload
		self.lost_frames = 0
		self.total_frames = 1
		# See mark_lost()'s comment -- opt-in per tracker instance (default off, matching
		# every existing caller's behavior unchanged) since it trades away useful
		# constant-velocity prediction through occlusion for subjects whose motion really
		# is roughly ballistic (a walking person), which only pays off for subjects whose
		# velocity is NOT a reliable predictor a few frames later (hands).
		self.freeze_velocity_on_loss = freeze_velocity_on_loss
		# Confirmation delay (SORT's min_hits pattern): a track needs `min_hits` TOTAL
		# matched frames while it has stayed alive before callers should treat it as a
		# real, displayable object -- this is what actually suppresses one-off noise
		# detections, which essentially never get a second real match at all before
		# track_buffer prunes them. Deliberately NOT a consecutive streak: `hits` only
		# stops incrementing on a missed frame (mark_lost()), it doesn't reset -- a
		# genuine object recovered via ByteTrack's low-confidence stage-2 pass (or just
		# re-matched after a brief gap) keeps the progress it already earned rather than
		# having to land a perfect back-to-back run, which this scene's real signal
		# (tuned to run right at the noise floor) can't reliably guarantee even for real
		# people. `confirmed` is sticky (set once, never cleared) so a track that already
		# earned confirmation doesn't flicker back to "unconfirmed" during occlusion --
		# that's what track_buffer/lost_frames already governs.
		self.hits = 1
		self.min_hits = min_hits
		self.confirmed = self.hits >= self.min_hits

	@property
	def box(self):
		"""Current [x1, y1, x2, y2] estimate (Kalman-predicted/updated, not raw detection)."""
		return _xyah_to_xyxy(self.mean[:4])

	def predict(self):
		self.mean, self.covariance = Track._kf.predict(self.mean, self.covariance)

	def update(self, box, score, payload):
		self.mean, self.covariance = Track._kf.update(self.mean, self.covariance, _xyxy_to_xyah(box))
		self.score = score
		self.payload = payload
		self.lost_frames = 0
		self.total_frames += 1
		self.hits += 1
		if self.hits >= self.min_hits:
			self.confirmed = True

	def mark_lost(self):
		self.lost_frames += 1
		self.total_frames += 1
		# hits deliberately NOT reset here -- see the confirmation-delay comment in
		# __init__ for why a missed frame only pauses progress toward min_hits rather
		# than wiping it out.
		# Freeze box SCALE (aspect ratio + height velocity, mean indices 6/7) the moment a
		# track goes unmatched. Without this, predict()'s constant-velocity model keeps
		# compounding whatever va/vh it last estimated every single lost frame with no
		# detection ever around to correct it -- and that estimate is least trustworthy on
		# exactly the tracks most likely to still be carrying a bad one: young tracks with
		# only one or two real observations behind them (still poorly conditioned,
		# high-covariance velocity terms), where a single noisy detection can produce a
		# spuriously large va/vh that then free-runs into runaway box growth. Position
		# (vcx/vcy, indices 4/5) is left alone -- a lost track's last known movement
		# direction is still useful to keep predicting. This self-corrects instantly on
		# the next real match: update() overwrites the whole mean from the fresh
		# measurement, velocity included.
		self.mean[6] = 0.0
		self.mean[7] = 0.0
		# Optionally freeze POSITION velocity too (vcx/vcy, indices 4/5) the moment a track
		# goes unmatched -- opt-in via freeze_velocity_on_loss, off by default. A walking
		# person's velocity a few frames into an occlusion is still a decent predictor of
		# where they'll re-emerge (roughly ballistic motion), so leaving vcx/vcy alone helps
		# there. A HAND's velocity is a much worse predictor of its position even 2-3 frames
		# later -- fast, erratic, frequent direction reversals -- so continuing to extrapolate
		# whatever velocity it had the instant before disappearing can drift the predicted
		# box well outside the real reappearance position, dropping IoU below match_thresh
		# and forcing a brand-new track ID instead of reacquiring the old one. Freezing
		# position at last-known-good instead (holding still) keeps the predicted box
		# anchored near where re-detection is actually likely to land.
		if self.freeze_velocity_on_loss:
			self.mean[4] = 0.0
			self.mean[5] = 0.0


# ==================== TRACKER ====================

_PAYLOAD_EXCLUDE = ('box', 'score')


def _payload_of(detection):
	return {k: v for k, v in detection.items() if k not in _PAYLOAD_EXCLUDE}


class ByteTracker:
	"""Multi-object tracker using ByteTrack's two-stage association. Call .update(detections)
	once per frame; detections is a list of dicts with 'box' [x1,y1,x2,y2], 'score', and any
	number of extra payload keys (kept as-is on the matched Track's .payload). Returns the
	list of currently active Track objects (order not significant)."""

	def __init__(self, high_thresh=0.5, low_thresh=0.1, match_thresh=0.7, track_buffer=30,
			max_detections=50, max_tracks=50, min_hits=1, freeze_velocity_on_loss=False):
		self.high_thresh = high_thresh
		self.low_thresh = low_thresh
		self.match_thresh = match_thresh  # min IoU to accept a match
		self.track_buffer = track_buffer  # frames a lost track survives before removal
		# Consecutive matched frames a brand-new track needs before Track.confirmed flips
		# true (see Track's own docstring/comment). Default 1 = confirmed on first
		# detection, i.e. today's original no-delay behavior -- opt-in via a caller
		# raising this. Changing it only affects tracks created AFTER the change; each
		# Track captures its own min_hits at creation, same as every other tunable here
		# only applying going forward.
		self.min_hits = min_hits
		# See Track.mark_lost()'s comment -- off by default (unchanged behavior for every
		# existing caller), passed down to each Track at creation same as min_hits.
		self.freeze_velocity_on_loss = freeze_velocity_on_loss
		# Hard, code-level safety caps -- independent of how low a caller's confidence
		# thresholds get tuned. The assignment step is O(n^3) in the larger of (tracks,
		# detections); an uncapped noisy scene can push that into the hundreds, and a
		# single call at n~300 costs roughly (300/100)^3 ~ 27x a call at n=100 (~22ms
		# measured), i.e. several hundred ms -- run synchronously on TD's main thread,
		# that's a multi-second UI freeze, not just a dropped frame. Confirmed live: this
		# exact failure mode froze TD repeatedly (watchdog logs showed FROZEN ticks with
		# the cook counter still advancing -- one blocking call, not a real deadlock).
		self.max_detections = max_detections
		self.max_tracks = max_tracks
		self.tracks = []

	def update(self, detections):
		for t in self.tracks:
			t.predict()

		if len(detections) > self.max_detections:
			detections = self._cap_detections(detections)

		high = [d for d in detections if d['score'] >= self.high_thresh]
		low = [d for d in detections if self.low_thresh <= d['score'] < self.high_thresh]

		all_idx = list(range(len(self.tracks)))

		# Stage 1: every current track vs. high-confidence detections.
		unmatched_tracks, unmatched_high = self._associate(all_idx, high)

		# Stage 2: tracks still unmatched vs. low-confidence detections -- recovers
		# occluded/blurred objects a confidence-thresholded detector alone would drop.
		unmatched_tracks, _ = self._associate(unmatched_tracks, low)

		for i in unmatched_tracks:
			self.tracks[i].mark_lost()

		for j in unmatched_high:
			d = high[j]
			self.tracks.append(Track(
				d['box'], d['score'], _payload_of(d),
				min_hits=self.min_hits, freeze_velocity_on_loss=self.freeze_velocity_on_loss,
			))

		self.tracks = [t for t in self.tracks if t.lost_frames <= self.track_buffer]

		# Second safety cap: if churn (spurious detections constantly spawning new tracks
		# before they age out via track_buffer) still pushes the track count too high,
		# drop the stalest/least-confident ones rather than let the NEXT frame's cost
		# matrix grow unbounded on top of an already-large detection count.
		if len(self.tracks) > self.max_tracks:
			# Ascending: freshest (lowest lost_frames) first, highest score breaks ties.
			self.tracks.sort(key=lambda t: (t.lost_frames, -t.score))
			self.tracks = self.tracks[:self.max_tracks]

		return self.tracks

	def _cap_detections(self, detections):
		"""Cut detections down to max_detections, but protect any detection that
		plausibly matches an EXISTING track before falling back to a flat score cut.
		A pure top-K-by-score cap can starve an already-confirmed track of its own
		matching detection on a noisy frame with many other candidates ranked higher by
		raw score -- that shows up downstream as the track going a frame unmatched,
		which ages every one of its keypoints' hold-frame counters (see
		onnx_yolo26_pose.py's postprocess()) regardless of confidence thresholds.
		Keeping every detection near a live track first avoids that."""
		if not self.tracks:
			return sorted(detections, key=lambda d: d['score'], reverse=True)[:self.max_detections]

		track_boxes = np.array([t.box for t in self.tracks])
		det_boxes = np.array([d['box'] for d in detections])
		best_iou_per_det = _iou_matrix(det_boxes, track_boxes).max(axis=1)
		near_existing_track = best_iou_per_det > 0.05

		relevant = [d for d, keep in zip(detections, near_existing_track) if keep]
		other = sorted(
			(d for d, keep in zip(detections, near_existing_track) if not keep),
			key=lambda d: d['score'], reverse=True,
		)
		return (relevant + other)[:self.max_detections]

	def _associate(self, track_idx_list, dets):
		"""IoU-distance + Hungarian matching between the given track indices and dets.
		Matched tracks are updated in place. Returns (still_unmatched_track_indices,
		unmatched_det_indices_into_dets)."""
		if not track_idx_list or not dets:
			return list(track_idx_list), list(range(len(dets)))

		track_boxes = np.array([self.tracks[i].box for i in track_idx_list])
		det_boxes = np.array([d['box'] for d in dets])
		cost = 1.0 - _iou_matrix(track_boxes, det_boxes)

		row_ind, col_ind = linear_sum_assignment_thresh(cost, thresh=1.0 - self.match_thresh)

		matched_rows = set(row_ind.tolist())
		matched_cols = set(col_ind.tolist())
		for r, c in zip(row_ind, col_ind):
			ti = track_idx_list[r]
			d = dets[c]
			self.tracks[ti].update(d['box'], d['score'], _payload_of(d))

		unmatched_tracks = [track_idx_list[r] for r in range(len(track_idx_list)) if r not in matched_rows]
		unmatched_dets = [c for c in range(len(dets)) if c not in matched_cols]
		return unmatched_tracks, unmatched_dets


# ==================== SHARED CUSTOM-PAR HELP TEXT ====================
# Every ONNX inference script in this project (onnx_yolo26_pose.py, onnx_yolo26_obj_det.py,
# onnx_yolo26_seg.py, onnx_yunet.py) exposes the same core set of ByteTracker-related custom
# pars in its onSetupParameters(), with help text that's identical except for the tracked
# "thing" (person/object/face) and the occasional model-specific caveat. Centralized here
# instead of copy-pasted four times so the wording only needs updating in one place.
#
# Not every script uses every key here (e.g. onnx_yolo26_pose.py collapses Confthreshold/
# Lowconfthreshold into one par with genuinely different semantics, so it writes that help
# text inline rather than forcing an inaccurate fit into this template) -- that's fine, this
# covers the common case, not every case.

_PAR_HELP_TEMPLATES = {
	'Confthreshold': (
		"Minimum detection confidence to start/confirm a new track (ByteTracker's high-"
		"confidence threshold -- see object_tracker.py). Detections below this can still "
		"recover an EXISTING track down to Low Confidence Threshold, but never start a "
		"brand-new one."
	),
	'Lowconfthreshold': (
		"ByteTracker's second-stage recovery threshold. Detections scoring between this and "
		"Confidence Threshold can't start a new track, but CAN re-match an already-existing "
		"track through a bad frame (occlusion, motion blur) that a single-threshold detector "
		"would just drop. Detections below this are discarded as background."
	),
	'Nmsiouthreshold': (
		"IoU threshold for collapsing near-duplicate raw detections of the same {subject} "
		"before they ever reach the tracker. Lower = more aggressive merging (risks merging "
		"two close-together {subject_plural}); higher = more duplicates survive to become "
		"phantom tracks."
	),
	'Minboxwidth': (
		"Minimum detection box width (fraction of frame width) to keep at all -- rejects "
		"degenerate slivers regardless of confidence. Separate from Min Box Height on "
		"purpose: {shape_note}"
	),
	'Minboxheight': (
		"Minimum detection box height (fraction of frame height) to keep at all -- see Min "
		"Box Width for why this is a separate threshold rather than one shared value."
	),
	'Tracklossframes': (
		"How many consecutive unmatched frames a track survives (Kalman-predicted position, "
		"no real detection) before being dropped entirely. Higher = more grace through "
		"occlusion, but also more frames of a possibly-wrong predicted position/scale before "
		"giving up."
	),
	'Trackiouthreshold': (
		"Minimum box overlap (IoU) required to accept a match between an existing track and "
		"a new detection. Too low risks a new {subject}'s detection getting absorbed into an "
		"unrelated existing track; too high breaks continuous matching and causes constant "
		"track-ID respawning."
	),
	'Trackconfirmframes': (
		"Total matched frames (not necessarily consecutive) a brand-new track needs before "
		"it's trusted and shown at all. Filters out single-frame noise \"detections\" that "
		"almost never get a second real match. Higher = slower to show a genuinely new "
		"{subject}, but cleaner."
	),
	'Outputsmoothing': (
		"Extra lerp on {what} on top of the tracker's own Kalman estimate -- pure cosmetic "
		"jitter damping. 0 = raw/no smoothing, 1 = frozen in place."
	),
}


def par_help(key, subject='object', subject_plural=None, what='box position/size', shape_note=None, extra=None):
	"""Build a custom par's help text (Par.help) from the shared template for `key` (see
	_PAR_HELP_TEMPLATES). `subject`/`subject_plural` fill in the tracked-thing word (e.g.
	'person'/'people', 'object'/'objects', 'face'/'faces' -- subject_plural defaults to
	subject+'s', override it for irregular plurals like 'person'). `what` and `shape_note`
	fill in the two templates that need model-specific detail (Outputsmoothing,
	Minboxwidth). `extra` appends one more script-specific sentence after the shared
	template, for a caveat that doesn't apply everywhere (e.g. why a default differs here).

	Raises KeyError if `key` has no shared template -- add one there instead of writing
	the help text inline again."""
	text = _PAR_HELP_TEMPLATES[key].format(
		subject=subject,
		subject_plural=subject_plural or f'{subject}s',
		what=what,
		shape_note=shape_note or '',
	)
	if extra:
		text = f"{text} {extra}"
	return text


# ==================== SHARED PER-TRACK STATE / DRAW HELPERS ====================
# These were each copy-pasted near-identically into several onnx_*.py scripts
# (onnx_yolo26_pose.py, onnx_yolo26_obj_det.py, onnx_yolo26_seg.py, onnx_yunet.py,
# onnx_hsemotion.py, onnx_opencv_hands.py, onnx_mediapipe_face.py) -- centralized here
# since none of them have any model-specific logic.

import colorsys


def track_color(track_id):
	"""Deterministic, maximally-distinct RGB (0-1) color per track_id, via the golden-
	ratio hue trick (successive ids land far apart around the hue wheel instead of
	clustering). Same formula every caller used independently before this was shared."""
	hue = (track_id * 0.6180339887498949) % 1.0
	return colorsys.hsv_to_rgb(hue, 0.85, 1.0)


def prune_stale(active_ids, *state_dicts):
	"""Delete entries for any track_id no longer in `active_ids` from each of
	`state_dicts` -- the standard "drop per-track held state once its track is gone"
	cleanup every script runs once per per-track dict (box/landmark/keypoint/emotion/
	presence/handedness state, etc.), after computing this frame's active track set."""
	for d in state_dicts:
		for tid in list(d.keys()):
			if tid not in active_ids:
				del d[tid]


def box_smooth(state_dict, track_id, box, smoothing):
	"""EMA-smooth a 4-element [x1,y1,x2,y2] box into state_dict[track_id] (created on
	first sight, lerped toward `box` by `smoothing` on every call after) and return the
	(mutable, in-place) smoothed list. Same lerp every caller used independently."""
	smoothed = state_dict.get(track_id)
	if smoothed is None:
		smoothed = list(box)
		state_dict[track_id] = smoothed
	else:
		for k in range(4):
			smoothed[k] = smoothed[k] * smoothing + box[k] * (1.0 - smoothing)
	return smoothed


def track_fade(lost_frames, track_buffer):
	"""Opacity multiplier (0.3-1.0) for drawing a track that's currently lost/predicted
	rather than freshly detected -- fades toward (not to) transparent as lost_frames
	approaches track_buffer, floored at 0.3 so a still-alive predicted track never goes
	fully invisible. Same formula every draw_tracked_*() method used independently."""
	if lost_frames <= 0:
		return 1.0
	return max(0.3, 1.0 - lost_frames / max(track_buffer, 1))


def td_to_px(td_x, td_y, width, height):
	"""Convert a TD-space (bottom-up Y, 0-1 normalized) coordinate to top-down pixel
	coordinates for cv2 drawing -- the same `to_px` closure every draw_tracked_*()
	method redefined locally."""
	return int(td_x * width), int((1.0 - td_y) * height)
