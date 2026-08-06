# Face/hand landmark mesh distortion on non-square canvases — FIVE root causes (two hit twice), all needed fixing

**Symptom:** MediaPipe FaceMesh's Debug COMP visualization, when composited directly over the
original source video (`/project1/comp13`, `over` composite of `out_passthrough` under
`out_debug`), showed landmarks/box clearly misaligned with the real face — the mesh appeared
squished vertically and stretched horizontally relative to the actual face, and separately the
detection box itself looked too wide/short (confirmed on the hand side too: "vertically squished,
way smaller than actual hand"). The same symptoms showed up in `onnx_opencv_hands.py`'s hand
mesh/box once built. This took three rounds to fully resolve, each only surfaced by directly
comparing against a real face/hand rather than reasoning abstractly: an initial camera-only fix
(Bug 1) was necessary but not sufficient; fixing the landmark rotation math (Bug 2) fixed the mesh
shape but the detection BOX was still visibly wrong; only checking the box's raw `w`/`h` values
directly (finding them exactly equal, frame after frame) surfaced Bug 3, a separate bias in the
detector's own box-size output.

## Bug 1 (real, but not the main cause at the time): Debug COMP camera's `sy = 0.5 * aspect`

`cam1` (a `cameraCOMP`) uses `orthowidth=2.0` for its orthographic projection, and its own
object-level `sx`/`sy` **Scale** parameters (Xform page — the camera's own 3D transform scale, not
a projection/FOV parameter; see [Camera_COMP docs](https://docs.derivative.ca/Camera_COMP)) were
set to `sx=0.5`, `sy=0.5 * op('../constant2')['aspect']`. Confirmed via empirical A/B testing
against a real face (bracketing `sy` across `0.281, 0.5, 0.889, 0.9, 1.0, 1.1, 1.778`) that
`sy=1.0` (plain constant, no aspect dependency) looked correct at the time, and the shipped `0.889`
value visibly compressed the mesh. Fixed (at the time) by setting `cam1.par.sy = 1.0` as a flat
constant in both `onnx_mediapipe_face.py`'s and `onnx_opencv_hands.py`'s Debug COMPs.

**Correction (see "Bug 5" below): `sy=1.0` was never actually aspect-independent — it was a
coincidence of the specific input aspect being tested at the time.** The real, general
relationship is `sy = sx * aspect` (a live expression, not a constant) — for whatever the source
video's aspect was during this original bracketing test, `sx * aspect` happened to equal
(or land very close to) `1.0`, which is exactly why a flat `sy=1.0` constant tested as "correct"
then and silently broke once the input aspect changed significantly (a near-square input).
Bracket-testing a few candidate constant VALUES found a value that worked for ONE aspect; it did
not (and structurally could not) reveal that the underlying relationship was aspect-dependent,
since the test never varied the input's own aspect ratio.

**This fix alone was not enough** — after applying it, the mesh was better but still visibly wrong
relative to a real face's actual proportions, which led to finding Bug 2.

## Bug 2 (the main cause): rotation-aligned landmark crop computed in the wrong (distorted) pixel space

**Root cause:** the working buffer these scripts feed the detector/landmark models is a
*non-uniformly stretched* square (`fit_square_sm` with `fit='fill'`, e.g. squishing a 640x360
source into 256x256 — different scale factors per axis: `scale_x = 256/640`, `scale_y = 256/360`).
For a **plain axis-aligned** quantity (a detection box's position or size), a fraction computed in
this distorted square space is mathematically IDENTICAL to the same fraction in the true,
undistorted source frame — the two different per-axis scale factors cancel out of the ratio. This
is why the detection box (drawn as a plain rectangle, never rotated) always looked fine, and why an
earlier, purely-algebraic pass concluded "no correction needed" — that conclusion was correct, but
only for axis-aligned quantities.

It does NOT hold for the landmark model's **rotation-aligned crop**. Aligning a face/hand crop
requires rotating by an angle computed from two reference keypoints (eye line, or wrist→middle-MCP)
— and rotating within an *anisotropically stretched* pixel grid (`scale_x != scale_y`) is not the
same transform as rotating in the true, undistorted frame. It introduces real shear. Every one of
the 468 (or 21) landmark points coming out of that crop inherits this shear once mapped back to
normalized output coordinates — which is exactly why the `cv2` debug overlay (drawn directly in the
square buffer's own, internally-consistent distorted space) looked anatomically correct, while the
Debug COMP's geo-instanced mesh (the same landmark data, now interpreted as true-frame-normalized
fractions on a true-aspect canvas) showed a mesh clearly wider than its own detection box.

**Fix:** in `_run_landmarks_batch` (both `onnx_mediapipe_face.py` and `onnx_opencv_hands.py`), do
the rotation/scale/center math for the crop entirely in **true (pre-square) pixel units** — fetched
each frame via `self.scriptOp.parent().op('null_passthrough').width/height` — and compose the
final affine as `A = scale * R(-angle) @ D`, where `R` is the correct TRUE-space rotation matrix
and `D = diag(true_w/square_w, true_h/square_h)` converts the square buffer's actual pixel data
(the only thing `cv2.warpAffine` can sample from) into true-pixel-equivalent terms before applying
the rotation. The inverse mapping (landmark-model output back to normalized coordinates) runs the
same correction in reverse: invert `A` to get back to square-pixel space, then multiply by `D`
again to convert to true-pixel space before dividing by the true dimensions. Box/keypoint
*positions* used only for axis-aligned purposes (the detection box itself, feeding the rotation
angle's input keypoints) still use fraction values directly against the true dimensions — no
`D` needed there, consistent with the axis-aligned-quantities argument above.

Confirmed live with a real face and hand, composited directly over source video: after this fix,
landmarks precisely traced eyes/nose/mouth/jawline (face) and fingers/palm outline (hand), stable
as the subject moved and turned.

**This fix corrected the mesh shape, but the detection BOX (drawn as a plain rectangle, and used
as `w`/`h` in `table_output`) was still visibly wrong** — too wide/short for both face and hand —
which led to finding Bug 3.

## Bug 3 (a second, unrelated model-bias issue): the detector's box-size regression is architecturally isotropic

**Root cause:** confirmed by reading `table_output`'s raw `w`/`h` values across many consecutive
live detections: **`w` exactly equals `h`, every single frame**, for both the face and hand
detectors. This isn't coincidence or an approximate training bias — it's architectural. BlazeFace/
BlazePalm's `fixed_anchor_size=true` design means each anchor's box regression is tied to a single
implicit "scale" concept applied to both dimensions, not two independent width/height values — the
model fundamentally assumes/produces a roughly SQUARE box in its own square input space.

The axis-aligned-fraction-preservation argument from Bug 2 (fraction-of-square ==
fraction-of-true-frame) is mathematically correct for POSITION, and even for SIZE *in principle* —
but only if the model's own raw output faithfully reflects the true, distorted appearance of the
object. It doesn't, here: because `w_fraction` always equals `h_fraction` in square-space by
construction, naively reprojecting them independently (`width_true = w_fraction * true_w`,
`height_true = h_fraction * true_h`) produces a box whose aspect ratio is **always exactly the true
frame's own aspect ratio** (e.g. a detection with `w=h=0.1633` reprojects to `104.5 x 58.8px` on a
640x360 frame — a 1.778:1 ratio, exactly `640/360`) — regardless of what the real face/hand
actually looks like. This is a genuinely different class of bug from Bug 2: not a coordinate-
transform error (there is no "correct" independent true width/height to recover — that information
was never in the model's output to begin with), but a model-architecture bias interacting badly
with the anisotropic stretch.

**Fix:** treat the model's single size value as describing an **isotropic true-pixel size** (the
same absolute pixel size on both axes, matching what the model's own architecture assumes), then
re-express it as a fraction of each axis's own true dimension rather than reprojecting the square
fractions independently:

```python
true_aspect = true_w / true_h
iso_w = box_w_square_fraction / math.sqrt(true_aspect)
iso_h = box_h_square_fraction * math.sqrt(true_aspect)
```

Applied to the OUTPUT-facing box (`boxes_td` / `table_output`'s `w`/`h`, and hence the Debug COMP's
rectangle) — the internal `box_native` (square-fraction, used for tracker IoU matching) is left
untouched, since IoU-based matching only needs internal consistency frame-to-frame, not correctness
against the true frame. Confirmed live: face and hand detection boxes now look properly
proportioned (face box taller than wide, hand box no longer "vertically squished") instead of
universally inheriting the source frame's own wide aspect ratio.

**Correction to this section:** an earlier version of this fix claimed the landmark-crop code (Bug
2's `_run_landmarks_batch`) "doesn't need the box to be isotropic, just approximately the right
size/location for cropping margin" and left its `box_w`/`box_h` (used only for choosing the crop's
`side` length, i.e. its zoom/margin) uncorrected. That was wrong — see Bug 4 below.

## Bug 4 (a consequence of Bug 3 in a different spot): the landmark crop's own size was still using the biased box dimensions

**Symptom:** reported separately, after Bugs 1-3 above were already fixed: face landmarks
"sometimes fit pretty good... but most of the time feel really scaled up" relative to the real
face — noticeably better when the head was tilted back, worse in a normal/frontal pose.

**Root cause:** `_run_landmarks_batch` computes the rotation-aligned crop's size as
`side = max(box_w, box_h) * roi_scale`, where `box_w`/`box_h` were still being computed the SAME
naive, biased way as Bug 3's `table_output` box (`box_native[2]*true_w - box_native[0]*true_w` for
width, `*true_h` for height) — not yet using the isotropic correction. Since the model's box
regression always outputs equal width/height fractions in square-space (Bug 3), and `true_w`
(640) > `true_h` (360) for this project's source video, `box_w` is *always* the larger of the two
— meaning `side` always used the width-based (frame-aspect-inflated) value, making the crop
systematically ~33% larger (`sqrt(640*360)` vs. `640`, for this specific resolution) than it should
be. A landmark model shown a crop that's more zoomed-out than it expects sees the real face
occupying a smaller fraction of its input than during training — a domain mismatch that can
plausibly bias its own output landmarks larger than the real face, similar in spirit to Bug 3 but
manifesting inside the landmark model's predictions rather than in a raw detection box.

**Fix:** apply the exact same isotropic-size formula used for the output box to the crop-sizing
`box_w`/`box_h` too, in both `onnx_mediapipe_face.py` and `onnx_opencv_hands.py`'s
`_run_landmarks_batch`:

```python
box_w = box_w_square_fraction * true_w / math.sqrt(true_aspect)
box_h = box_h_square_fraction * true_h * math.sqrt(true_aspect)
```

(For hands, this also fixes the `shift_x_px`/`shift_y_px` ROI-shift calculation, which multiplies
by `box_h` — it was inheriting the same bias.) Confirmed live with a 4-face test video (faces at
different sizes/angles/distances) — the largest, most direct-facing test face tracked essentially
perfectly (eyes/nose/mouth/chin precisely traced) after this fix, with the other three (smaller,
angled, partially occluded) within normal detection variance rather than showing the previous
systematic oversizing.

**Takeaway:** Bug 3's isotropic-size fix had to be applied *everywhere* the detector's box
width/height feeds into a downstream calculation, not just the one place (the output-facing box)
that was checked first — the same biased quantity was silently reused in a second location
(crop sizing) that produced a different-looking symptom (mesh scale vs. box shape), which is why
it wasn't caught until reported separately.

## Bug 5: `cam1.par.sy=1.0` was a hardcoded constant that only coincidentally matched the ORIGINAL test aspect — switching to a near-square input aspect reintroduced severe vertical squish

**Symptom:** reported live: "the hand tracking keypoints look great on a 16/9 aspect ratio input,
but the output is really vertically squished on a more square aspect ratio." First investigated by
eyeballing Debug-COMP-only renders (no source-video reference) and nearly concluded there was NO
bug at all, since a raw box aspect ratio (`w`/`h` ≈ 1.08, not obviously squished) and a first
synthetic corner-injection test (`(0,0)`/`(1,0)`/`(0,1)`/`(1,1)`/`(0.5,0.5)` written directly into
`table_landmarks`, bypassing live tracking, then read back via `TOP.numpyArray()`) both looked
correct at first — a real false-alarm retraction happened mid-investigation before the actual bug
was pinned down. The eventual, unambiguous reproduction came from overlaying the mesh directly on
the source video (`/project1/comp12`) with a hand held palm-out, fingers straight up: the real
fingertips reached near the top of frame, but the tracked mesh's fingertips stopped far short,
around the middle knuckles — a clear, large (not subtle) undershoot specific to points farther
from the wrist.

**Root cause, confirmed by precise measurement, not guessing:** injecting known, evenly-spaced test
points into `table_landmarks` and measuring their ACTUAL rendered pixel centroids (via
`np.where()`/`scipy.ndimage.label()` on the rendered TOP's own `numpyArray()`, not eyeballing)
showed every point's rendered Y position pulled toward the vertical center of the canvas, by an
amount proportional to its distance from center — the signature of a Y-axis SCALE error, not a
shear/rotation error. Solving for the actual effective scale from multiple independent test points
gave a highly consistent ~540 (not the correct ~998, the canvas's actual pixel height) — and
`540 = 998 * sy` for `sy=1.0`... no: solving the OTHER direction, the value of `sy` that produces
the CORRECT scale (998) turned out to be `sy = sx * aspect = 0.5 * 1.082 = 0.5411` — the exact
value briefly tested earlier in the same investigation (then mistakenly reverted back to `1.0`,
re-introducing the bug, when `1.0` was wrongly assumed to be the known-good baseline). Re-running
the corner-injection test with `sy` back at `1.0` reproduced the SAME scale-of-~540 distortion the
real hand showed — proof the camera, not the tracked data, was the actual fault, and that the
data itself had been fine (misleadingly so) the whole time.

**Why the earlier "false alarm" (see above) didn't catch this:** the first corner-injection test
happened to run at a moment when `sy` was transiently set to the correct `0.5411` value (from an
experiment earlier in the same debugging session) — so it validated the render pipeline as
correct, which was true AT THAT MOMENT, but gave false confidence that persisted after `sy` was
(mistakenly) reset back to `1.0` afterward. **Takeaway inside a takeaway:** a synthetic ground-
truth test is only trustworthy if you know EXACTLY what state the system was in when you ran it —
re-verify the same test again immediately before trusting its result for a *current* conclusion,
especially after any intervening parameter change.

**Fix:** changed `cam1.par.sy` from a hardcoded `CONSTANT` value to a live `EXPRESSION`:
`me.par.sx * op('../constant2')['aspect']` — so it automatically tracks whatever the live input
aspect actually is, instead of requiring a human to notice and re-tune a magic constant every time
the input resolution changes. Applied to `onnx_opencv_hands.py`'s Debug COMP; confirmed via a
fresh corner-injection test (exact canvas-edge alignment restored) and against the real
fingers-up hand pose (fingertips now precisely reach the real fingertips in the source-video
overlay).

**Not yet fixed, but confirmed to have the identical hardcoded `sy=1.0` constant**:
`MediaPipeFaceLandmarks/Debug/cam1` (and likely `YOLO26_POSE/Debug/cam1` and any other Debug COMP
copied from the same template — see Bug 1's original spot-check). Any of these will silently
reproduce this exact squish if their own input aspect drifts from whatever it happened to be when
each was last eyeballed as "looking fine." Worth sweeping all of them to the same `sy` expression
rather than waiting for each to be independently reported.

**Takeaway:** a hardcoded constant that empirically "tested correct" against ONE input is not
evidence the underlying relationship is actually constant — it's only evidence that the constant
matches the correct value for the specific conditions tested. When a formula-derived value and an
empirically-bracketed constant happen to agree, prefer keeping the relationship as a live
expression (reacting to whatever the true independent variable is) rather than baking in the
coincidentally-matching number, even if the number "looks right" in front of you right now.

## Bug 6: YuNet needed Bug 3's isotropic box-size fix too, despite NOT having BlazeFace/SCRFD's architectural excuse

**Symptom:** reported live on a portrait (1080x1920) input: YuNet's `table_output` bounding box
looked vertically stretched, while HSEmotion (a separate face detector on the same project, same
`fit_square_sm`-into-a-square preprocessing pipeline) looked correct on the same input. Both
detectors decode boxes the same structural way -- independent `x1,y1,x2,y2` (or `x,y,w,h`)
regression, normalized against the square buffer's own dims, no forced-equal-anchor architecture
like BlazeFace/BlazePalm. Since neither detector has Bug 3's specific "architecturally isotropic"
excuse, it looked at first like Bug 3's fix (never ported to `onnx_yunet.py`) shouldn't be needed.

**Root cause, confirmed by direct pixel-size calculation, not guessing:** on a real live detection,
`table_output` showed `w=0.1845`, `h=0.2059` (square-space fractions, ratio 0.896 -- nearly
square). Reprojected independently against `true_w=1080`/`true_h=1920` (`w*true_w`, `h*true_h`):
`199px x 395px`, a `0.50` width/height ratio -- far more elongated than a real face's ~0.75-0.9.
The near-square *fraction* ratio (0.896) was itself the tell: even without an architectural
constraint, YuNet's own regression, shown a severely anisotropically-squished portrait face (the
`fit='fill'` square buffer compresses height ~1.8x more than width for a 9:16 input), empirically
produces a close-to-square box in square-space -- and reprojecting a close-to-square fraction pair
independently against a true frame whose axes differ by ~1.8x inherits nearly that entire ratio as
apparent elongation, regardless of the real face's shape. HSEmotion's SCRFD-style anchor-distance
regression apparently doesn't exhibit this same near-square tendency under the same squish (or does
so less severely) -- a genuine per-model behavioral difference, not a shared coordinate bug.

**Fix:** applied the exact same isotropic-size formula as Bug 3/4 (`iso_w = w_frac / sqrt(true_aspect)`,
`iso_h = h_frac * sqrt(true_aspect)`, `true_aspect = true_w/true_h`) to `onnx_yunet.py`'s
`postprocess()`, computing `true_w`/`true_h` from the sibling `null_passthrough` TOP the same way
`onnx_mediapipe_face.py` already does. Only `w`/`h` are corrected -- `cx`/`cy` (and the corner
columns `x_left`/`x_right`/`y_top`/`y_bottom`, which don't feed the Debug COMP's box render at all)
are left as plain position fractions, since Bug 2's position-fraction-preservation argument holds
regardless of any given detector's box-size behavior. Confirmed live: reprojected box went from
`199x395px` (0.50 ratio) to `259x284px` (0.91 ratio) on the same portrait input, with zero errors.

**Takeaway:** Bug 3's "architecturally isotropic" framing was true for BlazeFace/BlazePalm
specifically, but the isotropic-size correction is really a fix for *any* detector whose square-
space box-size output happens to be roughly isotropic under a severe input-aspect squish -- which
can happen empirically even without a forced-equal-anchor architecture. "This detector's box
regression is independent, so it doesn't need Bug 3's fix" is not a safe inference; check the raw
square-space `w`/`h` fraction ratio directly (near 1.0 is the tell) before ruling it out, especially
under an aspect as extreme as portrait video.

## Combined takeaway

All three fixes were independently necessary — reverting any one of them (camera `sy` back to
`0.889`, the landmark math back to naive square-space rotation, or the box back to naive
per-axis reprojection) visibly reintroduced a distortion even with the other two fixes in place.
Don't assume a single plausible-looking fix (especially one found via parameter-bracketing rather
than root-cause analysis) is complete — re-verify the *combination* holds, and take a report like
"the box looks right but the mesh doesn't" or "the mesh is right now but the box still isn't" as a
strong signal that there are *multiple, independent* bugs stacked on top of each other, not one
root cause with several symptoms. Concretely: a coordinate-transform bug (Bug 2, exactly fixable)
and a model-architecture-bias bug (Bug 3, only heuristically compensable, since the true
information was never in the model's output) can coexist in the same pipeline and require
different kinds of fixes — solving one doesn't imply the other is solved too, even when both
produce a superficially similar "looks stretched" symptom.

## Process note — don't trust documentation-derived reasoning over direct measurement for a parameter interaction you don't fully understand

The first attempt at the camera fix reasoned from `Camera_COMP`'s docs to a guess (`sy` should
just equal `sx`) without a real face in frame to check against — the snapshot came back blank,
which was actually just "no face currently in view" (confirmed separately), but was momentarily
misread as "the fix broke rendering." A second documentation-based guess (that `sy=aspect` was
intentionally compensating for TD's own automatic ortho/aspect derivation) also turned out wrong
once tested against a real face. Only bracketing concrete values against one fixed real-world
reference converged on the right answer — and even that wasn't the whole story until the user's
own more precise diagnosis (comparing the `cv2` debug view against the geo-instanced mesh) pointed
at the real, larger bug. When a report includes a specific, testable claim ("X looks right, Y
doesn't"), verify that claim directly rather than continuing to iterate on the theory already in
hand.
