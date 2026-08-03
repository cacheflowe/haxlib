# MediaPipe Landmark Models (FaceMesh / Hand Landmark)

## What MediaPipe's own source actually does differently for hand duplicate suppression (researched, not guessed)

**Context:** after several rounds of tuning `onnx_opencv_hands.py`'s own dedup passes, still
saw an occasional phantom hand box (much smaller, sharing fingertips with the real hand) that
survived every fix so far, prompting the question: MediaPipe's own web demo (Tasks Hand
Landmarker) doesn't show this at all -- what's actually different in their real graph? Researched
via the real `google-ai-edge/mediapipe` GitHub source rather than assumption:

- `palm_detection_cpu.pbtxt`'s `NonMaxSuppressionCalculator` uses `algorithm: WEIGHTED`, not
  plain greedy suppression -- overlapping candidates get score-weighted-averaged into one
  consensus box rather than "keep the highest scorer, discard the rest." `overlap_type:
  INTERSECTION_OVER_UNION`, `min_suppression_threshold: 0.3` (same IoU-based test we already
  use). **Caveat found by direct measurement**: some diagnosed phantom/real pairs here have
  near-ZERO IoU (boxes don't actually overlap, just sit adjacent) -- so even MediaPipe's own
  WEIGHTED algorithm, gated on IoU overlap the same way ours is, likely would NOT merge every
  instance of this specific failure mode either. This is real MediaPipe behavior, but it's not
  a complete explanation on its own.
- `hand_landmark_tracking_cpu.pbtxt` uses a `GateCalculator` + `PreviousLoopbackCalculator` +
  `NormalizedRectVectorHasMinSizeCalculator` to **skip running palm detection entirely** once
  enough hands are already tracked from the PREVIOUS frame, only re-triggering detection when a
  tracked hand's presence drops/is lost. **Important limitation confirmed by testing against a
  live repro**: this gate only helps once you're already AT the tracked-hand-count cap from a
  prior frame -- it does nothing for the actual reported case here (one real hand + a phantom,
  both appearing on the SAME first frame, well under `max_num_hands`). A fresh reset-and-retest
  live confirmed both the real and phantom detection spawn as separate tracks together on frame
  1 regardless of any "already enough hands tracked" gating, since there's no prior-frame state
  yet to gate against.

**Conclusion:** MediaPipe's architecture-level tricks (WEIGHTED NMS, detection-skip-when-
already-tracked) are real and worth partially adopting (see the two fixes below), but neither
fully explains why the official demo doesn't show this artifact in the exact single-hand,
first-frame scenario reproduced here. The most likely remaining explanation is that Google's own
shipped/compiled model (used by the actual web Tasks API) is simply better-calibrated against
this specific sub-region false-positive than this project's third-party OpenCV Zoo ONNX
conversion of the same architecture -- a factor outside this project's control without a
different model source. Two concrete, partially-effective mitigations were still implemented:

1. **Match-against-existing-tracks filter** (in `postprocess()`, before `tracker.update()`):
   candidates without a strong native-space IoU match to any existing track (i.e. ones that
   would otherwise spawn a brand-new competing track) are checked against ALL existing tracks'
   own persisted `box_native`/`rot_keypoints_native` via the same center+orientation test
   `_dedup_by_center_distance` uses -- a match means "probably the same hand at the wrong
   assumed scale," so it's dropped rather than allowed to spawn a new track. This is the closest
   analog to MediaPipe's gate that's tractable without restructuring `ONNXInferenceManager`'s
   always-on worker loop, and DOES help for phantoms that appear a few frames after a real
   track is already established (confirmed empirically it does nothing for same-first-frame
   duplicates, which is why the raised `ANGLE_DEDUP_DIST_FACTOR` below was still needed).
2. Raised `ANGLE_DEDUP_DIST_FACTOR` from 1.3 to 2.0 (see the section below) -- the mechanism that
   actually has a chance to fire on frame 1, since it doesn't depend on any track already
   existing.

**Takeaway:** before assuming a reference implementation's better behavior comes from a specific
algorithmic trick, check whether that trick's own preconditions actually apply to your specific
failure case -- a genuinely real, correctly-researched architectural difference (the detection-
skip gate) turned out not to be the explanation for the exact scenario being debugged, confirmed
by testing the hypothesis live rather than stopping at "found it in their source code."

## Center-distance dedup missed a small phantom hand box that outscored the real, larger hand box it overlapped

**Symptom:** a small phantom hand box would appear directly on top of a real tracked hand,
sharing its fingertip region, surviving both standard NMS AND the existing center-distance dedup
pass meant specifically to catch this class of duplicate.

**Root cause:** `_dedup_by_center_distance` processes candidates in descending score order and,
for each kept box, suppresses any other box whose center falls within `dist_factor *
sizes[i]` -- using ONLY the just-kept box `i`'s own size for the radius. This silently assumes
the higher-scoring box is always the larger one. It isn't always: a tight, clean-looking crop
around just the fingertips/knuckles can score confidently, sometimes MORE confidently than the
real, larger hand box containing it. When that happens, the small phantom gets kept first, and
its own tiny size produces a suppression radius far too small to reach the real hand box's
center -- so the real box is never suppressed, and both survive side by side. Standard IoU-based
NMS doesn't catch this either, since IoU between a small nested box and a large containing box is
naturally low (intersection ~= small box's area, union ~= large box's area) regardless of score
ordering.

**Fix:** made the suppression radius symmetric -- `dist_factor * max(sizes[i], sizes[j])` for
each pairwise check, not just `sizes[i]`. Now whichever box in the pair is larger determines the
radius, independent of which one happened to score higher that frame.

**Takeaway:** a dedup/suppression pass whose radius derives from "whichever candidate we process
first" (typically score order) is implicitly assuming score correlates with the property the
radius is supposed to represent (here, box size) -- when that assumption breaks (a small, clean
crop scoring higher than the real object containing it), the pass can silently let a duplicate
through. Prefer a symmetric, pairwise-derived radius/threshold when the property that should
drive suppression isn't the same one used to pick processing order.

### Follow-up: even the fixed radius missed pairs whose CENTERS were genuinely far apart, and picking "whichever seeded the merge" as survivor was still wrong

Live-diagnosing a real paused frame (raw palm-detector output captured via temporary
instrumentation, not guessed) found this same phantom failure mode has two more layers:

1. **Wrist/middle-MCP keypoints can disagree even more than box centers do** -- a diagnosed pair
   had wrist keypoints ~0.16 apart (farther than their ~0.146 box-center distance), so no
   position-based radius alone could safely be widened to cover it without merging separate real
   hands. But the pair's predicted rotation ANGLE (wrist->middle-MCP vector) agreed within ~2-10
   degrees across multiple diagnosed instances -- a coincidence a genuinely separate hand is very
   unlikely to share purely by chance. **Fix:** `_dedup_by_center_distance` gained an orientation-
   agreement path (`Anglededuprange`, `ANGLE_DEDUP_DEG=20`) -- pairs whose rotation angle nearly
   matches get a more lenient merge radius (`ANGLE_DEDUP_DIST_FACTOR`, raised live from an
   initial 1.3 to 2.0 after a second diagnosed instance sat ~1.7x pair-size apart). **Real
   tradeoff, not a free win**: widening this radius also risks merging two GENUINELY SEPARATE
   real hands with similar orientation held close together (a prayer/clasped-hands pose) into
   one detection -- this needs to be tested against real two-hand poses, not just against the
   phantom case it was tuned for.
2. **The merge was still keeping the wrong box.** After fixing the radius, the SAME phantom
   (which usually scores higher) still won every merge as the literal "seed" that the greedy
   suppression loop happens to keep -- so the single surviving detection was consistently the
   undersized phantom box, not the correctly-scaled real hand. **Fix:** restructured the
   function from greedy "keep the seed, suppress its neighbors" into "cluster same-object
   candidates, then pick whichever CLUSTER MEMBER has the largest box as the representative" --
   score correlates with "looks like a confident hand crop," not with "correctly captures the
   whole hand's true extent," so size is a better correctness proxy than score once you already
   know two candidates are the same object.

**Also implemented, addressing a different but related gap**: candidates that don't directly
IoU-match any EXISTING track (i.e. about to spawn a brand-new track) are now ALSO checked against
every existing track's own persisted `box_native`/`rot_keypoints_native` via this same
center+orientation test, dropping ones that look like a duplicate of an already-tracked hand --
inspired by (though not identical to) MediaPipe's own detection-skip-when-already-tracked gate
(see the section above). **Confirmed via live testing this does NOT help when the phantom and
the real hand both appear together on the very first frame** (no prior track exists yet to check
against) -- it only helps for phantoms that appear a few frames into an already-established
track, so the raised `Anglededuprange` above is still the primary fix for the reported case.

## MAX_HANDS's output-trim step evicted a genuinely-occluded hand in favor of a fresher spurious detection, defeating Tracklossframes' own grace period

**Context:** a lost-but-not-yet-pruned `Track` already stays fully alive through
`Tracklossframes` -- `postprocess()`'s `confirmed`-inclusion check only filters on
`score`/`confirmed` (both unaffected by `mark_lost()`), and `write_tracks_to_table()`/
`write_landmarks_to_table()`/`write_bones_to_table()` write everything in `self.tracked_objects`
unconditionally, with no `lost_frames` filter anywhere. So the underlying data pipeline was
already designed to hold a hand's last-known box/landmarks steady through a brief occlusion --
the question was why that didn't fully prevent visible flicker.

**Root cause:** the `max_hands` output-trim step (`if len(confirmed) > max_hands:`) sorted
candidates by `(lost_frames ascending, -score)` and kept only the top `Maxhands` -- a sort order
originally chosen to fight BlazePalm's phantom-duplicate-track problem (see the section below):
prefer currently-detected tracks over stale Kalman-predicted ghosts. But that same ordering means
a real hand mid-occlusion (`lost_frames > 0`, since it's not currently matching a detection) sorts
*behind* any brand-new spurious detection that manages to slip past NMS/dedup that frame
(`lost_frames == 0`, fresh) -- so the instant total confirmed tracks exceeds `Maxhands`, the
genuinely-tracked occluded hand gets trimmed out of the output entirely for that frame, even
though the underlying `Track` object is still alive and being predicted. This directly fights
`Tracklossframes`' whole purpose and reads as flicker, since it's an output-list eviction, not a
track-death.

**Fix:** changed the trim sort to `(-total_frames, lost_frames, -score)` -- established
seniority (how long a track has been real) now wins the tiebreak first, with `lost_frames`/score
only breaking ties among similarly-established tracks. A real hand with dozens/hundreds of
`total_frames` behind it now always outranks a `total_frames=1` spurious detection for one of the
`Maxhands` slots, regardless of which one currently has `lost_frames == 0` -- solving both
problems at once: phantom tracks (which are new by definition, low `total_frames`) still lose to
real established tracks, and a briefly-occluded real hand no longer gets evicted by noise.

**Takeaway:** "prefer fresher detections" and "prefer established tracks" are different
tie-breaking philosophies that can each be right for a different failure mode (phantom-duplicate
suppression vs. occlusion-flicker prevention) -- when a fix for one problem (see the phantom-hand
section below) becomes a sort key reused elsewhere, revisit whether it still serves the NEW
problem's intent before assuming a shared mechanism is fine as-is.

## Landmark smoothing only ran on inference frames, so raising Landmarkinterval made motion steppier instead of just cheaper

**Symptom:** with `Landmarkinterval` above 1 (throttling how often the landmark model actually
re-runs, to save GPU submissions -- see the FPS section below), the displayed hand mesh visibly
stepped/stuttered once every N frames instead of moving smoothly, worse at higher intervals.

**Root cause:** `postprocess()`'s EMA smoothing (`prev * smoothing + landmarks * (1-smoothing)`)
lived INSIDE the `if ... % landmark_interval == 0:` block -- it only ran on the frames a real
inference happened. Every frame in between just held `self._landmark_state` completely static
(no interpolation at all), then the next real inference's EMA blended toward the new target in
one lump step. The user reasonably expected the interval to trade real-inference-rate for
compute, with smoothing making up the difference on the in-between frames -- instead the
in-between frames did nothing, and the interval directly controlled how often (and how far) the
output visibly jumped.

**Fix:** split "latest raw inference result" from "displayed value." `_landmark_target_state`/
`_handedness_target_state` now hold the raw result, updated only on real inference frames (same
as before). `_landmark_state`/`_handedness_state` (the values actually read for output/ROI
derivation) are now updated via the SAME EMA lerp toward that target, but in a separate loop that
runs EVERY frame regardless of `landmark_interval` -- so the display value keeps easing toward
a fixed target across all the in-between frames instead of holding still and then snapping.

**Takeaway:** an "update every N frames, hold last value between" throttle and "smooth the
output" are two different concerns that both touched the same EMA line here -- collapsing them
into one conditional block meant the smoothing silently stopped doing its job exactly when the
throttle made it most necessary. When a value is both throttled and smoothed, keep a target/
displayed split so the smoothing pass can run on its own cadence (every frame) independent of
how often the target itself actually changes.

## Brief hand occlusion spawns a new track ID instead of reacquiring the old one, even well within Tracklossframes' budget

**Symptom:** a hand disappearing for just a handful of frames (brief occlusion, hand dipping past
frame edge) would come back as a brand-new track ID rather than the same one continuing --
despite `Tracklossframes` (track_buffer) defaulting to 15, far more than enough frames for the
track to still be alive and waiting to be reacquired.

**Root cause:** the track WAS still alive (not pruned -- `track_buffer` wasn't the issue at all),
but re-association failed. `object_tracker.py`'s shared `ByteTracker`/`Track` uses a
constant-velocity Kalman box model: every unmatched ("lost") frame, `predict()` keeps
extrapolating the track's last-known velocity (`Track.mark_lost()` already froze the box-SCALE
velocity terms to prevent runaway growth, see the comment there, but deliberately left
POSITION velocity alone since "a lost track's last known movement direction is still useful to
keep predicting" -- true for the tracker's other callers, e.g. a walking person). A hand's
velocity is a poor predictor of its position even 2-3 frames later -- fast, erratic, frequent
direction reversals -- so continuing to extrapolate whatever velocity it had the instant before
disappearing drifts the predicted box outside the real reappearance position within just a few
frames, dropping IoU below `match_thresh` (`Trackiouthreshold`) and forcing stage-1 association to
treat the reappearing detection as brand new rather than a match.

**Fix:** added an opt-in `freeze_velocity_on_loss` flag to both `Track` and `ByteTracker` in
`object_tracker.py` (default `False` -- every existing caller's behavior is unchanged). When
enabled, `mark_lost()` also zeroes the position-velocity terms (`mean[4]`/`mean[5]`, alongside the
scale-velocity terms it already zeroed) -- holding the predicted box at its last-known position
instead of continuing to extrapolate. Enabled only in `onnx_opencv_hands.py`'s `ByteTracker`
construction, not the shared default, since the other trackers in this project (people/pose,
faces) track subjects whose short-term motion really is closer to ballistic/constant-velocity,
where the un-frozen behavior is a genuine benefit, not a bug.

**Takeaway:** a shared tracker's "helpful" motion-prediction assumption is only helpful for
subjects whose real motion matches that assumption. Before tuning IoU/confirmation thresholds to
chase a track-ID-stability problem, check whether the *prediction* itself is drifting off target
during the gap -- a Kalman constant-velocity model will confidently keep going in the wrong
direction for an object that doesn't actually move that way, and no amount of threshold-tuning
fixes a bad prediction, only masks it by making matching sloppier overall (which risks merging
different objects instead).

## Stability at odd hand angles: derive the landmark-model ROI from the PREVIOUS frame's own landmarks, not a fresh palm-detector box every frame

**Symptom:** the user compared `onnx_opencv_hands.py`'s live tracking against Google's own
MediaPipe Tasks web demo (`hand_landmarker`) and found ours noticeably less stable at odd hand
angles — the official demo held a clean mesh through rotations/edge-on poses ours would jitter or
lose on.

**Root cause:** the script re-ran full BlazePalm detection on the whole frame every single frame
and fed that box straight into `_run_landmarks_batch` as the landmark model's crop ROI — so a
frame where the palm detector's own box regression struggled with an angled/rotated/edge-on hand
(a real, expected weak point of that architecture) directly disturbed the landmark crop, even for
an already-well-tracked hand. This is architecturally different from MediaPipe's OWN hand-tracking
pipeline: once a hand is tracked, MediaPipe derives the next frame's landmark-model ROI directly
from that hand's OWN previous 21 landmarks (wrist + middle-finger MCP for rotation, full landmark
bbox for position/size) and only falls back to re-running palm detection when the landmark model's
own `hand_confidence` ("presence") output — which we were decoding but silently discarding — drops
below a threshold (hand turned away, occluded, left frame).

**Fix:** two changes, both additive (no model swap, no architecture rewrite of the tracker):
1. Stopped discarding `lmk_out[1]` (`hand_confidence`, already sigmoid-applied per this export) —
   now stored per-track as `self._presence_state[track_id]`, deliberately *unsmoothed* since it
   gates next frame's ROI source and needs to react immediately to a presence drop, not lag an EMA.
2. `_run_landmarks_batch` now branches per hand: if that track has a held landmark result AND its
   last presence score was >= `Presencethreshold` (par, default 0.5), the crop center/size/rotation
   are derived directly from those held landmarks (bbox of all 21 points × `Landmarkroimargin`,
   default 1.6 — much smaller than the palm detector's own `Roiscale`=3.0, since the landmark bbox
   already spans the whole hand including fingers, unlike the detector's tight palm-only box) —
   bypassing the fresh palm-detector box entirely for that hand. Falls back to the original
   detector-box path otherwise (new track, or presence dropped). The palm detector still runs every
   frame regardless (still needed to feed ByteTracker's IoU matching and catch newly-entering
   hands) — only the landmark model's OWN crop source changed.

**Verified live:** immediately after deploying, both actively-tracked hands showed presence scores
of ~0.99 (well above the 0.5 gate), confirming the landmark-derived path was engaged rather than
silently falling through to the old behavior, and a snapshot of two hands in a deliberately
awkward angled/touching pose showed both skeletons tracking cleanly.

**Takeaway:** when a from-scratch two-stage detector+landmark pipeline feels less stable than a
reference implementation of the "same" model, check whether the reference implementation actually
avoids re-running the detector once a track is established — MediaPipe's own hand/face tracking
graphs are built around exactly this "detect once, then track from the landmarks themselves"
pattern, and a naive per-frame redetect-and-feed-to-tracker architecture (reasonable and simpler to
build first) gives up a real stability advantage that has nothing to do with model accuracy itself.

## RESOLVED: the ~2-second freeze was specific to the Qualcomm AI Hub export of hand_detector.onnx — switching to OpenCV Zoo's independent export fixed it completely

After the extensive investigation below (GC, cuDNN algorithm search, cross-model contention,
submission-frequency throttling, an actual Windows/driver TDR check — all ruled out one at a time
with direct measurement, none of them fixed it), the real fix turned out to be much simpler than
anything at the ONNX Runtime / GPU-scheduling layer: **use a different ONNX export of the same
model**.

Key observation that pointed the way: the sibling BlazeFace model (`face_detector.onnx`, same
Qualcomm AI Hub export pipeline, same general depthwise-conv-heavy architecture family) never
showed this pathology, running fine at ~30fps the whole time. If the cause were CUDA, cuDNN,
GC, or GPU-scheduling contention with TD's renderer in general, the face model should have hit it
too. It didn't — which meant the problem was specific to `hand_detector.onnx`'s particular export,
not to the hardware/runtime/architecture family.

**Fix:** replaced `onnx_mediapipe_hands.py` (Qualcomm's `hand_detector.onnx` +
`hand_landmark_detector.onnx`, `data/ml/mediapipe/`) with `onnx_opencv_hands.py`, using OpenCV
Zoo's independently-converted export of the same MediaPipe Hands architecture
(`palm_detection_mediapipe_2023feb.onnx` + `handpose_estimation_mediapipe_2023feb.onnx`,
`data/ml/opencv_zoo/`, from https://github.com/opencv/opencv_zoo). Confirmed live: 0 outliers
over a 3-minute / 5152-sample instrumented window (max observed call: 26.5ms) — a complete
resolution, not just an improvement. `Effectivefps` also jumped to 50-70+ (vs. 13-25 with the
Qualcomm export), independent of and in addition to the freeze fix.

**Notable I/O differences from the Qualcomm export** (all confirmed via direct inspection before
writing any production code — see `onnx_opencv_hands.py`'s module docstring for the full list):
NHWC input layout (not NCHW), stock MediaPipe anchor config (192x192, 4-layer/`[8,16,16,16]`,
2016 anchors — confirmed by generating anchors independently and matching OpenCV's own hardcoded
anchor table exactly, no reverse-engineering needed unlike the Qualcomm export's 2944-anchor
grid), landmark output already in **crop-space pixels** (not normalized 0-1 like the Qualcomm
export — the opposite convention, see the section below), 224x224 landmark input (not 256), and
different ROI enlarge/shift tuning constants (`scale=3.0, shift_y=-0.4`, OpenCV's own values, not
MediaPipe's stock `2.6/-0.5`). Confirmed the landmark model's actual ONNX Runtime output order via
tracing the raw ONNX graph (`onnx.load()` + walking node inputs back from each graph output) rather
than trusting the reference script's variable-unpacking order — it happened to match here, but
that's not guaranteed by anything (`cv.dnn`'s output enumeration order isn't inherently the same
as onnxruntime's `get_outputs()` order) and is worth checking explicitly for any future model swap.

**Takeaway for future model integration work in this project:** when a specific ONNX export
exhibits a severe, hard-to-explain performance pathology that a same-architecture sibling model
doesn't share, seriously consider that the export itself (not the runtime, driver, or GPU
scheduling) is the actual variable — and that trying an independently-converted alternative export
of the same model may be far cheaper than continuing to debug the runtime layer. Both local
(CPU-only, opset-compatible) and live-TD (GPU) verification are worth doing for a replacement
candidate before switching — the local path here caught an actual would-be integration bug
(the pixel-space vs. normalized landmark unit convention) *before* ever touching the live project,
unlike the Qualcomm hand models, which could only be loaded/tested inside TD's own onnxruntime
(1.22.0) due to an opset incompatibility with the local dev conda env's older onnxruntime (1.17.1).

## BlazePalm produces phantom duplicate hand tracks for the same physical hand (multi-scale anchor jitter), tanking both correctness and FPS

**Symptom:** with exactly 2 real hands in frame (two fists close together), `table_output`
showed 5-7 simultaneously "confirmed" hand tracks, several sharing near-identical positions and
even the same handedness label (e.g. two separate tracks both reading "Right" a few percent of
image-width apart). `Effectivefps` on the parent COMP read ~11, well below the equivalent
per-instance cost seen on the face pipeline (2 hands at 256x256 crops vs 4 faces at 192x192 crops
should be *cheaper* per frame, not slower).

**Root cause:** each confirmed hand track costs one synchronous landmark-model `session.run()`
call in `postprocess()` — so 5-7 phantom tracks directly multiplied the per-frame inference cost
by 2.5-3.5x versus the real 2-hand case. The phantoms themselves come from BlazePalm's
multi-scale anchor grid (this export's reverse-derived 5-layer config, see the anchor-derivation
entry below) firing several genuinely high-confidence (0.9+) but differently-sized/positioned
detections for the *same* physical hand — worse than face's case because (a) two hands close
together in frame gives the detector an inherently more ambiguous scene, and (b) different anchor
scale groups can each "win" on different frames due to normal small variations in the input, so a
real hand's detections can bounce between anchor groups frame-to-frame, producing boxes whose
mutual IoU is often below any reasonable NMS threshold *and* below the tracker's own frame-to-frame
matching threshold — so instead of being merged, the "losing" detection either fails standard NMS
(same frame) or fails to match the existing track well enough (different frame) and spawns a brand
new phantom track, which then lingers via Kalman prediction for `Tracklossframes` frames even once
its own detections stop arriving.

**Fix (layered, in `onnx_mediapipe_hands.py`) — no single change was sufficient alone:**
1. A second **center-distance dedup pass** after standard IoU-based NMS
   (`_dedup_by_center_distance`, `CENTER_DEDUP_DIST_FACTOR=0.8`) — merges same-frame duplicates
   whose *centers* are close relative to their own size, even when IoU alone says otherwise.
   Alone this dropped 7 tracks to ~5 — not sufficient, since most fragmentation happens *across*
   frames, not within one.
2. **Lowered `NMS_IOU_THRESHOLD` (0.3→0.2) and `TRACKER_IOU_THRESHOLD` (0.3→0.15)**, and lowered
   `TRACKER_MAX_AGE` (30→15) so phantom tracks decay faster once their source detections stop
   winning. Dropped 5→3.
3. **A hard `MAX_HANDS` cap (default 2, matching MediaPipe's own high-level Hands API default of
   `max_num_hands=2`)**, applied *twice* — once on raw per-frame detections before tracking, and
   again on the final `confirmed` list right before landmark inference (sorted by
   `(lost_frames, -score)`, preferring currently-detected tracks over stale Kalman-predicted
   ones). The first application alone was insufficient: a track already confirmed can keep
   appearing in `tracked_objects` via prediction even on frames where the incoming detections are
   correctly capped, since old tracks aren't detections — they have to be capped again at the
   output-construction step. This was the change that actually got the live track count down to
   exactly 2, matching the real hand count.

**Takeaway:** for any detector with a wide multi-scale anchor grid over a scene with intentionally
close/ambiguous instances, expect the standard "NMS at detection time" story to be insufficient by
itself — fragmentation happens over time via the tracker too, and a final hard cap on the *output*
track count (not just the *input* detection count) is a legitimate, standard mitigation, not a
hack — MediaPipe's own production API does exactly this.

## GPU contention between two simultaneously-cooking ONNX networks measurably slows both down

**Symptom:** while investigating the hand-tracking FPS above, toggling `MediaPipeFaceLandmarks`'s
`allowCooking` off raised `MediaPipeHandLandmarks`'s `Effectivefps` only modestly (~13→17), but
re-enabling `MediaPipeFaceLandmarks` afterward caused *its own* `Effectivefps` to read ~6.9 — down
from ~30 when it had effectively had the GPU to itself. Both networks run their detector +
per-instance landmark inference via independent background worker threads
(`ONNXInferenceManager`'s per-COMP worker pattern), each with its own `onnxruntime`
`InferenceSession` using the CUDA execution provider.

**Status:** not root-caused or fixed — flagged here as a real, measured effect for whoever tackles
it next. Likely candidates: CUDA kernel execution serializing across separate host threads
issuing calls against separate sessions/contexts in the same process (no explicit CUDA stream
isolation configured anywhere in `onnx_util.providers()`), plain GPU compute/memory-bandwidth
saturation once two real-time detector+landmark pipelines run concurrently, or something specific
to how TD schedules multiple Script TOPs each with their own worker thread. Whether this is worth
addressing (e.g. shared session/stream management, one combined worker thread servicing both
COMPs, or accepting that running many live ONNX networks simultaneously in one `.toe` has a
combined throughput ceiling) is a project-level decision, not something to silently patch inside
either script.

### Follow-up: the dominant contention source is TD's own rendering, not the other ONNX network — and it's fixable per-script via update-interval throttling

Further live diagnosis (after the phantom-hand fix above still left hands at ~13-15fps, visibly
slow) found the actual bottleneck is bigger than cross-network contention: `last_inference_ms`
(the palm detector's own measured worker-thread cost) read **~30-55ms in real playback**, but
only **~4.6ms** when called from a `/run` script (which pauses TD's own cook loop while it
executes — an artificially uncontended snapshot). Disabling the *other* MediaPipe network barely
moved this number. Shrinking `Inputwidth` 256→192 (fewer anchors, less conv compute) *also* didn't
move it — ruling out raw compute cost and pointing to a roughly **fixed per-call overhead**
(consistent with the cross-thread/GPU-scheduling contention already flagged above), most likely
contention with TD's own continuous rendering, which never stops regardless of which ONNX
networks are active.

Since the tax is per-call and roughly fixed rather than proportional to work, the lever that
actually helps is **fewer total GPU submissions per second** — exactly the problem
`onnx_hsemotion.py`'s `EMOTION_INTERVAL` already solved for its (batched) emotion classifier.
Applied the same pattern to `onnx_mediapipe_hands.py`'s landmark model (`LANDMARK_INTERVAL`/
`Landmarkinterval`, default 3): throttle how often the landmark model actually re-runs, holding
each hand's last (`Outputsmoothing`-blended) reading between updates. Confirmed live: raised
`Effectivefps` from ~13-15 to ~22 with 2 tracked hands, with no obvious visual degradation (real
hand pose doesn't change meaningfully frame-to-frame at 30fps, same justification as
`EMOTION_INTERVAL`'s own help text). The palm detector itself wasn't throttled the same way — its
worker-thread queue already self-limits to whatever rate it can sustain (`is_inferencing` gating
in `onnx_inference_manager.py`), so an explicit interval there wouldn't add anything.

**Takeaway:** when a `/run`-script isolated timing test disagrees wildly with a model's real
production cost, suspect the isolated test is the misleading one (TD's own frame loop is paused
during synchronous `/run` execution) rather than concluding something is wrong with the
production code. And when per-call overhead looks roughly fixed regardless of input size, an
update-interval throttle (hold-last-value between periodic re-runs) is the right lever — not
attempts to make the model itself cheaper.

**Correction (see the "unresolved periodic multi-second freeze" section below):** the claim just
above ("the palm detector itself wasn't throttled... an explicit interval there wouldn't add
anything") turned out to be incomplete. A `detector_interval` mechanism WAS later added and tried
specifically to reduce total GPU submissions/second as a mitigation for a *different, more severe*
problem (multi-second freezes, not just lower fps) — and measured LIVE to make that problem
*worse*, not better. The FPS-focused reasoning in this section (fewer submissions → fewer
contention windows → smoother average throughput) still seems to hold for ordinary frame-to-frame
FPS variance, but does NOT explain or fix the qualitatively different multi-second stall — treat
those as two separate phenomena with different (and only partially understood) causes, not one
problem with a single fix.

## Unresolved: periodic multi-second full-app freezes, several root causes ruled out with direct evidence

**Symptom:** independent of ordinary FPS (which the fixes above did genuinely improve), TD would
periodically freeze *completely* for almost exactly ~2 seconds (2050-2100ms every time, unusually
consistent), then fully recover, recurring every 5-90+ seconds with no obvious pattern — reported
by the user as the whole app stalling, not just choppy video. Confirmed via Windows Event Viewer
that this is **not** a real GPU driver TDR reset (`Get-WinEvent` found zero matching System-log
events across a window that definitely contained multiple freezes) — the app itself never
actually loses its GPU context, so whatever this is, Windows/the driver never considered it a real
hang.

**Method:** wrapped `run_inference()` (the palm detector's own `session.run()` call) with a timer
recording every call's duration to a list, left it running for 1-3 minutes at a time, then
inspected the distribution for outliers — this surfaced the ~2075ms events cleanly (everything
else was 5-65ms) and let each hypothesis below be tested by comparing outlier *frequency* across
same-length windows before/after a change, rather than guessing from a single freeze.

**Ruled out, in order, each with a live before/after comparison:**
1. **Cross-network GPU contention** — disabling the *other* MediaPipe network (face) barely
   changed hands' `Effectivefps` or stall frequency. Not the cause, or at most a minor contributor.
2. **Python's cyclic garbage collector** — a full gen2 GC pass traversing TD's enormous live
   Python object graph looked like a strong match (consistent duration, periodic-ish recurrence).
   `gc.disable()` (see `onnx_inference_manager.py`, applied globally since this is a process-wide
   setting) showed 0 outliers over one 45-second window — looked like a confirmed fix — but a
   later, longer window with GC confirmed still disabled (`gc.isenabled()` checked directly, not
   assumed) showed 3 more ~2070ms outliers. The first clean window was a false negative from too
   short a sample, not a real fix. (The `gc.disable()` change itself was kept regardless — it's a
   reasonable thing to do in a real-time Python host independent of this specific bug, see that
   section's own comment in `onnx_inference_manager.py` for the tradeoff — but don't expect it to
   fix this particular symptom.)
3. **ONNX Runtime's cuDNN convolution algorithm search** — `onnxruntime.enable_profiling` captured
   an actual profile trace covering one of these freezes: `model_run` took ~1.9 seconds, almost
   entirely from 9+ individual small depthwise `Conv` nodes (input shape `[1,256,16,16]`) each
   taking ~200ms — an operation that should take low single-digit microseconds. This looked like
   exactly the "EXHAUSTIVE algorithm search re-triggering" pattern already known from this
   project's HSEmotion work, so `cudnn_conv_algo_search: 'HEURISTIC'` was set in
   `onnx_util.providers()` (confirmed via `session.get_provider_options()` that the new session
   actually used it). Outliers of the same ~2060-2100ms magnitude still occurred afterward. Kept
   the `HEURISTIC` setting anyway (it's a reasonable default with no observed downside), but it is
   NOT the fix for this symptom.
4. **A real GPU driver hang/TDR reset** — see Windows Event Viewer check above. Ruled out.
5. **Submission frequency (detector_interval throttle)** — tried explicitly reducing how often the
   palm detector submits new work to the worker thread (`ONNXInferenceManager.detector_interval`,
   analogous to the landmark model's own `LANDMARK_INTERVAL` throttle). Measured WORSE: 13 outliers
   over a 3-minute window at `detector_interval=2`, vs. 3 over a 2-minute window at
   `detector_interval=1`. This actively disproves the "fewer submissions = less contention = fewer
   stalls" theory for this specific symptom, even though a version of that reasoning (see the
   correction above) did produce a real, measurable *average*-FPS improvement for the landmark
   model. Reverted to `detector_interval=1` in `onnx_mediapipe_hands.py`.

**Current status: root cause NOT identified.** What's known: it's real GPU kernel execution time
(not a lock/wait, per the ORT profile), specific to whichever Conv nodes happen to be running at
that moment, roughly fixed in total duration (~2075ms) regardless of the mitigations tried above,
and doesn't correspond to any logged driver-level event. The most likely remaining explanation is
some form of GPU scheduling contention between the CUDA compute workload and TD's own real-time
rendering engine sharing one physical GPU (consistent with `_worker_loop`'s own pre-existing
comment about this being uncoordinated) — but every lever tried *from inside the ONNX/Python
layer* to reduce or avoid it has failed to help. The next thing worth trying is OS/driver-level,
not code-level: Windows 11's "Hardware-accelerated GPU scheduling" setting changes exactly this
kind of arbitration between a real-time graphics engine and a compute workload sharing one GPU,
and toggling it (Settings → System → Display → Graphics, requires a reboot) was proposed but not
yet tried as of this writing (deferred at the user's request to exhaust code-level options first —
which are now exhausted). If revisited, test with the same before/after outlier-frequency
methodology used above, not a single subjective impression.

**Symptom:** `face_landmark_detector.onnx` (FaceMesh, 468 points) loaded and ran without error,
detection boxes were correct, the rotation-aligned crop looked right when inspected visually —
but every tracked face's 468 landmarks collapsed into a single sub-pixel cluster after mapping
back to original-frame coordinates (`table_landmarks` showed ~0.0003-0.0005 normalized spread
per face, i.e. under 1px at a 256x256 working resolution, instead of the ~0.05-0.08 spread a real
face should produce). The Debug COMP's geo-instanced point cloud rendered as one dot per face
instead of a 468-point mesh.

**Root cause:** the model's `landmarks` output ([1,468,3]) is **normalized 0-1 relative to the
192x192 (or 256x256 for hands) input crop**, not raw crop-space pixel coordinates. The production
code's inverse-affine step assumed pixel-space output (mirroring the *forward* `cv2.warpAffine`
call, which genuinely does work in pixel space) and fed the raw `[0,1]`-range x/y straight into
the inverse transform built for pixel-space inputs — under-scaling every point by ~192x and
collapsing all landmarks toward the crop's local origin.

Confirmed live via a `/run` probe that called the loaded landmark session directly and printed
`session.run(None, {'image': chw})`'s raw output range: `output[1]` (landmarks) came back with
x/y confined to roughly `[0.14, 0.99]` for a 192x192 crop — clearly normalized, not pixel range.

**Fix:** scale the raw model x/y by the model's own input size before applying the inverse
affine:

```python
lm = lmk_out[1][0]  # (468, 3), x/y NORMALIZED 0-1 relative to the crop
xy_crop = lm[:, :2] * LANDMARK_INPUT_SIZE  # normalized -> crop-space pixels
xy_orig = (A_inv @ xy_crop.T).T + t_inv    # now correctly maps to original-frame pixels
```

**Why this is easy to miss:** a *standalone* single-crop verification (no inverse-mapping back to
original-frame coordinates) can look completely correct even with this bug present — the relative
*shape* of the 468 points plotted directly in normalized 0-1 crop space still looks like an
anatomically correct face (eyes, nose, mouth, jaw all in the right relative positions), because
the bug only manifests once you rescale those normalized values as if they were pixels and invert
a pixel-space affine. Only checking the round-trip back into original-frame coordinates (e.g. by
computing per-face min/max spread of the final output and comparing it to the known face box
size) surfaces the error.

**Applies to:** any MediaPipe-family landmark model reused in this project (this one hit
`face_landmark_detector.onnx` in [python/scripts/onnx_mediapipe_face.py](../../python/scripts/onnx_mediapipe_face.py);
`hand_landmark_detector.onnx`'s `landmarks` output ([1,21,3]) should be assumed to have the same
normalized-0-1 convention until proven otherwise for that specific export — verify with the same
raw-output-range probe before trusting the inverse-affine math, rather than re-assuming pixel
space again. **Do NOT assume this generalizes across exports though**: OpenCV Zoo's
`handpose_estimation_mediapipe_2023feb.onnx` (see the RESOLVED section at the top of this file)
turned out to output landmarks in the OPPOSITE convention — already crop-space PIXELS, not
normalized 0-1 — confirmed via the same raw-output-range probe before writing
`onnx_opencv_hands.py`. Every new export needs this check independently; there is no safe
"MediaPipe-family default" to assume either way.). **Confirmed applies to hands too**:
`onnx_mediapipe_hands.py` was written with the `* LANDMARK_INPUT_SIZE` scaling already in place
from the start (this doc having just been
written), and produced correct real-world landmark spread (~0.15-0.25 normalized per hand) on the
very first live test — no repeat of the bug, confirming the normalized-0-1 convention holds
across this whole model family.

## BlazePalm's anchor grid does not match MediaPipe's own published config — derive by anchor-count matching, then verify by detection-score signature

**Context:** `hand_detector.onnx` (BlazePalm, Qualcomm AI Hub export) outputs 2944 anchors for a
256x256 input. Stock MediaPipe's own `mediapipe/modules/palm_detection/palm_detection_cpu.pbtxt`
(confirmed via GitHub source) is a 4-layer SSD config (`strides=[8,16,16,16]`) at 192x192 input,
producing exactly 2016 anchors — this export's topology is genuinely different, not just a
resolution rescale of the stock config (unlike the face detector, where scaling MediaPipe's
128-input 4-layer config by 2x to a 256 input reproduced the exact 896-anchor topology).

**Approach:** solved for a stride/layer configuration whose *anchor count* (via the same
same-stride-layer-merging formula as `_generate_anchors`) matches 2944 exactly. A 5-layer config
with `strides=[8,16,32,32,32]` at 256x256 input computes to 2048+512+384=2944 — an exact match,
not an approximation. This was then verified against real detections (not just trusted because
the arithmetic matched): loaded `hand_detector.onnx` in TD's own `onnxruntime` (the local dev
conda env can't load this model at all — opset 21 unsupported there, confirmed only working in
TD's onnxruntime 1.22.0), ran it against a real hand frame from `data/videos/dancing.mp4`, and
got a tight cluster of near-identical high-confidence scores (top score 0.95, several others
0.83-0.93 within the same anchor neighborhood) — the same "clean cluster vs. scattered near-random
noise" signature that confirmed BlazeFace's anchors earlier in this project. A wrong anchor grid
produces detections that don't cohere this way even if a plausible-looking box happens to appear.

**Takeaway for future MediaPipe-family models:** don't assume a Qualcomm/qairt (or any other
third-party) re-export shares its anchor topology with MediaPipe's own published graph config,
even for the "same" model family. If the anchor *count* doesn't match a simple resolution-rescale
of the stock config, solve for stride/layer combinations that produce the right count
computationally, then verify with real detection data (score clustering, not just "an anchor
count matched" or "it decoded without crashing") before trusting the result.

## Testing ONNX/video code against the live TD process can crash or freeze the whole app — keep test scripts minimal and avoid blocking loops

**Symptom:** a `/run` script that combined `cv2.VideoCapture` (seeking + reading ~10 frames) with
CPU-based `onnxruntime` inference (10 sequential `session.run()` calls) in a single request caused
TD to become completely unresponsive, requiring the user to force-restart the whole application.
A second, much smaller script (`cv2.imread`/draw/`imwrite` on an already-decoded frame, no model
inference at all) also hung one request later. Both losses cost real work: unsaved live-network
changes (custom Debug-COMP wiring, `Inputwidth` pars, callback file pointers) made via `/run`
mutations earlier in the same session were wiped by the crash/restart, since they'd never been
saved to the `.toe`.

**Likely cause:** not conclusively root-caused (this repo already has an open
`TD_FREEZE_INVESTIGATION.md` for a separate pre-existing freeze issue), but the leading suspects
are (a) blocking TD's single main thread for an extended period with repeated video seeks +
CPU inference in one request, possibly tripping some internal watchdog/responsiveness check, and
(b) general instability this build of TD already has independent of this project's own code.

**Practical mitigations for future test/verification scripts run via `/run` against a live TD
project:**
- Test ONE frame / ONE inference call per request, not a loop over several — isolate cv2 file I/O
  from onnxruntime calls into separate requests first if something needs debugging, rather than
  combining both in a single script from the start.
- **Save the `.toe` (`POST /save`) before any test that touches CPU-heavy inference or video
  decode loops**, and again immediately after any significant unsaved live-network wiring (new
  COMPs, connectors, par changes made via `/run`) — don't let more than one meaningful change
  accumulate unsaved, since a crash mid-session silently reverts everything back to the
  last-saved state with no warning.
- If a `/run` request doesn't return within a reasonable window, treat the live TD process as
  possibly compromised — verify with a cheap `GET /network` call before issuing anything else,
  rather than assuming the original request is simply "still running."

## False lead ruled out: direct Table-DAT-as-`instanceop` DOES fan out N rows into N instances

While chasing the bug above, the single-dot-per-face symptom looked exactly like a
geometry-instancing problem (wrong instance count) rather than a coordinate problem — worth
recording so the next person doesn't re-walk the same dead end. A synthetic probe (5-row table,
widely-spaced x values, `instanceop` wired directly to the Table DAT) read back
`geo.par.numinstances.eval()` as `1` even right after configuring `instancecountmode='oplength'`,
which looked like confirmation that direct DAT sources can't drive per-row instancing and that a
`transpose` → `dattoCHOP` → `null` CHOP conversion (the pattern the box/rectangle debug widgets in
every Debug COMP in this project use) would be required instead.

That probe's `numinstances` reading was a red herring — the probe COMP was never actually
cooked/rendered (no camera/render TOP wired to it), so the par never recomputed from its default.
Once the real landmark-units bug above was fixed, the **unmodified** direct-DAT wiring
(`geo_landmarks.par.instanceop = in_landmarks`, a plain Table DAT, no CHOP in the chain) rendered
the full 468-point mesh per face correctly on the first try. Don't reach for the CHOP-conversion
pattern by default — it's one valid way to drive instancing (proven by the box/rectangle
widgets), but a Table DAT wired directly into `instanceop`/`instancesop`/`instancetop` is *also*
proven working (this file, `onnx_mediapipe_face.py`'s `Debug/geo_landmarks`) and is simpler to set
up for an already row-per-instance table. If per-instance data looks collapsed/wrong, check the
data going into the table before suspecting the instancing mechanism itself.
