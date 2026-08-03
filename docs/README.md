# Agent Learnings Log

Hard-won debugging discoveries that aren't covered by official docs. Read before debugging;
write an entry after solving anything non-obvious. See [CLAUDE.md](../CLAUDE.md) for format.

## Files

- [learnings/onnx-runtime.md](learnings/onnx-runtime.md) — ONNX Runtime / TouchDesigner: CUDA EP
  silently falling back to CPU due to cuDNN version mismatches with onnxruntime-gpu's cudnn
  frontend; a measured `arena_extend_strategy` regression; the input-to-output latency tuning
  investigation; and dynamic batch sizes re-triggering CUDA's per-shape algorithm search (see
  also [.ai/skills/td-threaded-inference-optimization.md](../.ai/skills/td-threaded-inference-optimization.md)).
- [learnings/mediapipe-landmarks.md](learnings/mediapipe-landmarks.md) — researched MediaPipe's
  real source (WEIGHTED NMS, GateCalculator/PreviousLoopbackCalculator skip-detection-when-
  already-tracked) to explain why their web demo doesn't show phantom hand duplicates -- found
  neither fully explains the diagnosed single-hand/first-frame repro case here, most likely
  attributable to their shipped model's own calibration. Implemented an orientation-agreement
  dedup path (rotation angle match -> wider merge radius) plus a cluster-then-pick-largest-member
  merge (score doesn't correlate with correct scale) plus a match-against-existing-tracks filter.
  Also: the center-distance phantom-hand dedup pass missed cases where a small phantom box
  scored HIGHER than the real, larger hand box it overlapped (radius was based only on the
  higher-scoring box's own size, implicitly assuming score correlates with size) -- fixed by
  using the pair's max size instead, symmetric regardless of score ordering. Also: the `Maxhands`
  output-trim step could evict a genuinely-occluded (but still tracked) hand from the output in
  favor of a fresher spurious detection, defeating `Tracklossframes`' own grace period -- fixed by
  sorting the trim by track seniority (`total_frames`) first instead of `lost_frames` first. Also:
  landmark output smoothing
  only ran on real-inference frames, so raising `Landmarkinterval` (throttling inference rate for
  perf) made motion steppier instead of just cheaper -- fixed by splitting "latest raw target"
  from "displayed/smoothed value," with the smoothing lerp now running every frame regardless of
  the interval. Also: brief hand occlusion was
  spawning a new track ID instead of reacquiring the old one because the shared `ByteTracker`'s
  constant-velocity Kalman prediction kept extrapolating a hand's last-known (erratic) velocity
  through the gap, drifting the predicted box past the real reappearance position -- fixed via an
  opt-in `freeze_velocity_on_loss` flag in `object_tracker.py`, enabled only for hands. Also:
  landmark-derived ROI persistence (derive the hand landmark model's crop from its OWN previous 21
  landmarks + a presence-score gate, not a fresh palm-detector box every frame) fixed angled-hand
  tracking stability to match MediaPipe's own reference behavior. Also: RESOLVED a severe ~2-second
  periodic TD freeze traced to the Qualcomm AI Hub export of the hand detector specifically (not
  CUDA/GC/GPU-scheduling in general — a sibling model from the same pipeline never showed it);
  switching to OpenCV Zoo's independent export of the same MediaPipe Hands architecture
  (`onnx_opencv_hands.py`) fixed it completely and roughly tripled FPS. Also covers: MediaPipe
  landmark models' x/y units vary by export (normalized 0-1 vs. crop-space pixels — check every
  time, don't assume), BlazePalm's phantom-duplicate-hand-track problem (fixed via layered
  NMS/tracker-threshold/max-hands-cap changes), and a false lead about Table-DAT-based geometry
  instancing.
- [learnings/debug-comp-camera-aspect.md](learnings/debug-comp-camera-aspect.md) — face/hand mesh
  AND box distortion on non-square canvases, FIVE root causes (two hit twice, in different code
  paths): (1) every ONNX Debug COMP's `cam1.par.sy` (`= 0.5 * aspect`) was hardcoded to a flat
  `1.0` constant — this "worked" only because it coincidentally matched `sx * aspect` for the
  ORIGINAL test video's aspect (only fixed for hands so far, see (5)); (2) the rotation-aligned
  landmark crop was computed in the square working buffer's own anisotropically-distorted pixel
  space instead of true (pre-square) pixel units, introducing real shear into every landmark; (3)
  the detector's box-size regression is architecturally isotropic (`w` exactly equals `h` in
  square-space, every frame) — naively reprojecting bakes the source frame's own aspect ratio
  into every detection box AND (4, a second occurrence of the same bug) into the landmark crop's
  own zoom/size, which read as "landmarks feel scaled up"; (5) switching to a near-square input
  aspect resurfaced (1) as a severe vertical squish — fixed for real this time by making `cam1.sy`
  a live expression (`sx * aspect`) instead of a hardcoded constant, confirmed via precise
  pixel-measurement (not eyeballing) after an initial false-alarm retraction mid-investigation.
  `MediaPipeFaceLandmarks/Debug/cam1` confirmed to have the same still-hardcoded `sy=1.0` and
  likely needs the identical fix. All fixed so far in `onnx_mediapipe_face.py` and
  `onnx_opencv_hands.py`.
