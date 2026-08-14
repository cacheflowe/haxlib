---
name: td-ml
description: Machine learning guidance for TouchDesigner projects. Use this when integrating ONNX, PyTorch, or model-driven workflows in TD.
---

# Machine Learning in TouchDesigner

Guide to running ML models (ONNX, PyTorch, TensorFlow) inside TouchDesigner.

## Documentation

- [CUDA in TD](https://derivative.ca/UserGuide/CUDA)
- [OpenCV in TD](https://docs.derivative.ca/OpenCV)
- [Custom Operator Samples (ONNX C++)](https://github.com/TouchDesigner/CustomOperatorSamples/tree/main/TOP/ONNXCandyStyleTOP)

## ONNX Runtime (Recommended)

The most practical path for running ML models in TD. Use `onnxruntime-gpu` for GPU acceleration.

### Installation

```bash
# Install with TD's Python for compatibility
& "C:\Program Files\Derivative\TouchDesigner\bin\python.exe" -m pip install onnxruntime-gpu==1.22.0 --target="../_local_modules"

# Or via pip with CUDA 11 index
pip install onnxruntime-gpu --extra-index-url https://aiinfra.pkgs.visualstudio.com/PublicPackages/_packaging/onnxruntime-cuda-11/pypi/simple/
```

Version 1.22.0 is confirmed GPU-compatible with the latest TouchDesigner. **Pin `nvidia-cudnn-cu12` explicitly** alongside it — leaving it unpinned lets pip resolve whatever cudnn 9.x point release is newest at install time, and some of those regress the CUDA execution provider's conv engine selection (silent fallback to CPU, no crash). Known-good combo:

```
onnxruntime-gpu[cuda,cudnn]==1.22.0
nvidia-cudnn-cu12==9.11.0.98
```

See [docs/learnings/onnx-runtime.md](../../docs/learnings/onnx-runtime.md) for the full failure signature and debugging steps.

### Integration Pattern

Typical flow: load ONNX model, run inference on a thread, pass results back to main thread via queue.

```python
import onnxruntime as ort
import numpy as np

# Load model
session = ort.InferenceSession('model.onnx', providers=['CUDAExecutionProvider'])

# Get input from TOP as numpy array
input_array = op('moviefilein1').numpyArray()

# Run inference (do this on a background thread for real-time)
results = session.run(None, {'input': input_array})

# Write results back to TD (on main thread)
op('script_top').copyNumpyArray(results[0])
```

### Useful Tools

- [Netron](https://netron.app/) — Visualize ONNX model architecture
- [ONNX Runtime docs](https://onnxruntime.ai/docs/install/)

## PyTorch

Possible but tricky due to CUDA compatibility. TD ships with CUDA in its `/bin` directory.

### Check Versions

```python
import torch
print(torch.version.cuda)     # e.g., '11.8'
print(torch.__version__)      # e.g., '2.7.1+cu118'
```

### Installation

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# Or via conda (resolves CUDA runtime automatically):
conda install conda-forge::cuda-runtime=12.8.0 conda-forge::cudnn=9.7.1.26
```

### Reference Projects

- [TDDepthAnything](https://github.com/TouchDesigner/TDDepthAnything) (official)
- [TDDepthAnything](https://github.com/olegchomp/TDDepthAnything) (community)
- [TDYolo](https://github.com/patrickhartono/TDYolo)
- [PyTorchTOP](https://github.com/DBraun/PyTorchTOP)

## TensorFlow

- Works on CPU only (Windows)
- GPU support is not available in TD's environment

## ONNX Model Sources

### Model Repositories

- [Qualcomm AI Hub](https://aihub.qualcomm.com/models) — optimized ONNX models
- [Hugging Face ONNX Community](https://huggingface.co/onnx-community/models)
- [Hugging Face ONNX Model Zoo](https://huggingface.co/onnxmodelzoo)
- [PINTO Model Zoo](https://github.com/PINTO0309/PINTO_model_zoo) — huge collection of converted models
- [Ultralytics](https://docs.ultralytics.com/integrations/onnx/) — YOLOv8 ONNX export

### Task-Specific Models

| Task | Model/Resource |
|------|---------------|
| Depth estimation | [Depth Anything V2](https://aihub.qualcomm.com/models/depth_anything_v2), [ONNX Depth Anything](https://github.com/fabio-sim/Depth-Anything-ONNX) |
| Segmentation | [BGNet](https://aihub.qualcomm.com/models/bgnet), [MediaPipe Selfie](https://aihub.qualcomm.com/models/mediapipe_selfie), [SAM2](https://github.com/ibaiGorordo/ONNX-SAM2-Segment-Anything) |
| Pose estimation | [RTMPose](https://github.com/open-mmlab/mmpose/tree/main/projects/rtmpose), [RTMPose (Qualcomm model)](https://huggingface.co/qualcomm/RTMPose-Body2d/tree/main), [E2Pose (PINTO)](https://github.com/PINTO0309/PINTO_model_zoo/tree/main/333_E2Pose/demo), [rtmlib](https://github.com/Tau-J/rtmlib) |
| Hand tracking | [MediaPipe Hands via OpenCV Zoo](https://github.com/opencv/opencv_zoo/tree/main/models/palm_detection_mediapipe) — **implemented**, see `python/scripts/onnx_opencv_hands.py` and `data/ml/opencv_zoo/` below (replaced an earlier Qualcomm AI Hub export that had a severe unresolved performance pathology — see `docs/learnings/mediapipe-landmarks.md`); [Hand Gesture Recognition](https://github.com/PINTO0309/hand-gesture-recognition-using-onnx) |
| Face analysis | [CavaFace](https://aihub.qualcomm.com/models/cavaface) |
| Face/hand landmarks | MediaPipe FaceMesh (468 pts, `onnx_mediapipe_face.py`) + Hand Landmark (21 pts + handedness, `onnx_opencv_hands.py`) — **implemented**, see `data/ml/mediapipe/` and `data/ml/opencv_zoo/` below |
| Emotion recognition | [HSEmotion / Emotion_onnx](https://github.com/Shohruh72/Emotion_onnx) — **implemented**, see `python/scripts/onnx_hsemotion.py` and `data/ml/hsemotion/` below |
| Eye gaze | [EyeGaze](https://aihub.qualcomm.com/models/eyegaze) |
| Object detection | [YOLOv7 Head](https://github.com/PINTO0309/PINTO_model_zoo/tree/main/322_YOLOv7_Head), [Wholebody](https://github.com/PINTO0309/PINTO_model_zoo/tree/main/472_DEIMv2-Wholebody34) |
| Optical flow | [NeuFlowV2](https://github.com/ibaiGorordo/ONNX-NeuFlowV2-Optical-Flow), [RAFT](https://github.com/ibaiGorordo/ONNX-RAFT-Optical-Flow-Estimation) |
| OCR | [EasyOCR](https://aihub.qualcomm.com/models/easyocr), [PaddleOCR ONNX](https://huggingface.co/monkt/paddleocr-onnx/tree/main) |
| Video matting | [RobustVideoMatting](https://github.com/PeterL1n/RobustVideoMatting) |
| Image inpainting | [LAMA Dilated](https://aihub.qualcomm.com/models/lama_dilated) |
| Foot detection | [FootTrackNet](https://aihub.qualcomm.com/models/foot_track_net) |
| Vision-language (VLM) | [SmolVLM-256M](https://huggingface.co/HuggingFaceTB/SmolVLM-256M-Instruct) — small, fast VLM |

### Google's official MediaPipe Tasks model bundles — a source distinct from community ONNX conversions

Every community ONNX conversion found so far (OpenCV Zoo, PINTO Model Zoo) is derived from
MediaPipe's older, openly-published **Solutions API** weights (~2020-2021). Google's current
**Tasks API** (what `mediapipe-samples-web`'s live demos actually run) ships separately-hosted
`.task` bundles that can be genuinely different models, not just repackaged/requantized versions
of the same weights — confirmed by direct inspection, not assumption (see below).

- **Download URL pattern**: `https://storage.googleapis.com/mediapipe-models/<task>/<task>/float16/1/<task>.task`
  (e.g. `hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task`,
  `face_landmarker/face_landmarker/float16/1/face_landmarker.task`). No auth needed.
- **A `.task` file is just a zip.** `unzip` it directly — no special MediaPipe tooling required.
  `hand_landmarker.task` contains `hand_detector.tflite` + `hand_landmarks_detector.tflite`.
  `face_landmarker.task` contains `face_detector.tflite` + `face_landmarks_detector.tflite` +
  `face_blendshapes.tflite` (a model with NO equivalent anywhere in this project's current
  pipeline — see below) + a geometry-pipeline metadata file.
- **Confirmed findings** (2026-08, comparing against this project's current models): the palm/face
  DETECTOR architectures are essentially identical to what's already integrated (same input res,
  same anchor count) — swapping likely wouldn't change much. But the **face landmark model
  differs meaningfully**: Google's current model is 256x256 input (vs this project's 192x192) and
  outputs **478 landmarks including 10 iris points** (`1434 = 478*3`), vs this project's 468-only
  model — a real capability gap, not just a recalibration. **`face_blendshapes.tflite`** is an
  entirely separate model (146 2D points in -> 52 ARKit-style blendshape coefficients out:
  `jawOpen`, `mouthSmileLeft`, `eyeBlinkLeft`, etc.) — the "how open/closed are eyes and mouth,
  what's the expression" question this project's own MAR/EAR-style geometric approximations were
  built to answer, but from an actual trained model instead of hand-tuned ratios. The hand landmark
  model is also somewhat bigger (likely the "full" vs "lite" capacity tier) than the OpenCV Zoo
  conversion currently in use. **Not yet converted/integrated** — flagged as follow-up work.

### Inspecting a `.tflite` model's architecture before committing to a conversion

Don't guess whether a model will convert cleanly — check its actual op list first. This needs
neither `tensorflow` nor `tflite-runtime` (often hard to install/unavailable for a given Python
version on Windows) — just the lightweight, pure-Python `tflite` + `flatbuffers` pip packages,
which read the FlatBuffer schema directly without needing an actual inference runtime:

```python
pip install tflite flatbuffers   # small, pure-Python, no tensorflow needed

from tflite.Model import Model
from tflite.BuiltinOperator import BuiltinOperator
from collections import Counter

code_to_name = {v: k for k, v in vars(BuiltinOperator).items() if isinstance(v, int)}
with open('model.tflite', 'rb') as f:
	model = Model.GetRootAsModel(f.read(), 0)
sg = model.Subgraphs(0)
print('inputs:', [sg.Tensors(sg.Inputs(i)).Shape(j) for i in range(sg.InputsLength()) for j in range(sg.Tensors(sg.Inputs(i)).ShapeLength())])
# ...op histogram: walk sg.Operators(i), resolve via model.OperatorCodes(op.OpcodeIndex()).BuiltinCode()
```

A model built entirely from standard ops (`CONV_2D`, `DEPTHWISE_CONV_2D`, `PRELU`, `FULLY_CONNECTED`,
`LOGISTIC`, `MEAN`/`SQUARED_DIFFERENCE`/`RSQRT` — the last three are just an unrolled LayerNorm,
still standard) converts cleanly via `tf2onnx`'s native TFLite import
(`python -m tf2onnx.convert --tflite model.tflite --output model.onnx --opset 13`) — no need for
a heavier multi-hop pipeline (e.g. PINTO0309's `tflite2tensorflow`) unless a genuine `CUSTOM` op
shows up in the histogram (rare for MediaPipe's own models; none were found across palm/hand/face
detector, hand/face landmark, or the face-blendshapes model despite its unusual non-image point
input). Heavy `DEQUANTIZE` op counts just reflect fp16-weight-quantized storage (one dequant per
weighted layer at load) — not a compatibility concern, and not evidence of custom ops either.

### TD-Specific ML Projects

- [TD-ONNX-EX](https://github.com/yeataro/TD-ONNX-EX)
- [TopArray](https://github.com/IntentDev/TopArray/)
- [venvBuilderTD](https://github.com/ioannismihailidis/venvBuilderTD/)
- [madmomTD](https://github.com/ioannismihailidis/madmomTD) — audio analysis (beat tracking, onset detection)
- [Real-Time ONNX in TD (tutorial)](https://derivative.ca/community-post/real-time-magic-integrating-touchdesigner-and-onnx-models/69856)

## Tips

- Always run inference on a **background thread** to avoid blocking TD's cook cycle
- Use `queue.Queue` to pass results back to the main thread (see [td-threading.md](td-threading.md))
- Match numpy version to what TD ships — incompatible versions crash `numpyArray()`
- Native ONNX via C++ custom operators is possible but requires building a custom plugin

## See Also

- [.ai/skills/td-threading.md](.ai/skills/td-threading.md) — Background thread patterns
- [.ai/skills/td-python-environment.md](.ai/skills/td-python-environment.md) — Installing packages, conda, venv

## TODO:
- Current upgrade
  - Comp par: Input Aspect Ratio: `op('./in1').width / op('./in1').height`
  - Debug font size: `parent(2).op('in1').height * 0.025`
  - Eval dat for score: `str(round(float(me.inputTable[me.inputRow, 1].val) * 100)) + '%'`
  - Debug cam1 scale: `0.5 * parent(2).par.Inputaspectratio`
- Fix up ByteTracker - it doesn't seem great
- Look into threaded frame sync delay - how can we tighten this up
  - Add frame delay controls for all? can we auto-detect?
- How can we mirror script params to parent comps?
- Add alternate objects in Yolo obj & seg outputs. Birds?

## Research / Links to check out

- Face det
  - https://huggingface.co/onnx-community/arcface-onnx
  - https://huggingface.co/garavv/arcface-onnx
  - https://github.com/zhongyy/SFace
  - https://huggingface.co/deven96/face_recognition_sface/tree/main
  - https://github.com/peiyunh/tiny (OLD)
- Head classification (hat, open mouth, sunglasses)
  - https://github.com/PINTO0309/PINTO_model_zoo/tree/main/495_Comprehensive-Head-Classification
- 
- Person segmentation
  - https://github.com/PierreMarieCurie/rf-detr-onnx
  - https://derivative.ca/community-post/tutorial/rf-detr-touchdesigner/74780
    - https://github.com/roboflow/rf-detr
- Landmarks
  - https://huggingface.co/qualcomm/Facial-Landmark-Detection
  - https://huggingface.co/Kijai/LivePortrait_safetensors/blob/main/landmark.onnx ??
  - Insightface: 2d106det.onnx
  - Eyes addon! 
    - https://aihub.qualcomm.com/models/eyegaze
    - https://github.com/LeeXuanHua/Eye-Gaze-Estimation-MPIIGaze/blob/main/convert_to_onnx.py
- Emotion -- **implemented**, see `python/scripts/onnx_hsemotion.py` (`/project1/HSEmotion`)
  - https://github.com/Shohruh72/Emotion_onnx/releases
    - HSEmotion is the emotion classifier (`data/ml/hsemotion/emotion.onnx`, 7-class softmax,
      260x260 input) -- this part's naming is fine, the repo/library name matches the file.
    - The FACE DETECTOR bundled in the same repo (`data/ml/hsemotion/detection.onnx`) is a
      **SCRFD-family** anchor-based FPN detector (confirmed live: 9 outputs -- score/bbox/kps x
      3 FPN strides [8,16,32], 2 anchors/location) -- NOT named or documented as SCRFD anywhere
      in the upstream repo or the file itself, easy to lose track of. Confirmed via
      `session.get_outputs()` against the real file, not from the repo's own docs (it doesn't
      name the architecture at all). If this ever needs replacing/upgrading, search for SCRFD
      checkpoints/exports specifically, not "Emotion_onnx" or "detection.onnx" -- those won't
      surface anything, since the pairing here is arbitrary (this repo just bundled a stock
      SCRFD detector alongside its own emotion classifier, they aren't co-trained).
- pose
  - https://github.com/namas191297/cigpose-onnx
  - https://github.com/ibaiGorordo/ONNX-Mobile-Human-Pose-3D
- Face/hand landmarks -- **implemented**, see `python/scripts/onnx_mediapipe_face.py` (multi-face,
  BlazeFace detector + FaceMesh 468-point landmarks, `data/ml/mediapipe/` -- Qualcomm AI Hub
  export) and `python/scripts/onnx_opencv_hands.py` (multi-hand, BlazePalm detector + 21-point
  hand landmarks + handedness, `data/ml/opencv_zoo/` -- **OpenCV Zoo** export, not Qualcomm).
  - Both follow the same two-stage architecture as `onnx_hsemotion.py` (threaded detector +
    synchronous per-instance landmark inference in `postprocess()`), plus a rotation-aligned
    crop step (align eye-line/wrist-to-middle-MCP to a fixed axis via `cv2.warpAffine` before
    landmarking) and an inverse-affine step mapping landmarks back to original-frame coordinates.
  - **The hand model went through two different ONNX exports.** The first (Qualcomm AI Hub,
    `data/ml/mediapipe/hand_detector.onnx` + `hand_landmark_detector.onnx`) had a severe,
    unresolved performance pathology -- individual tiny depthwise Conv nodes periodically took
    ~200ms each (vs. microseconds normally), causing ~2-second full-TD freezes every 5-90
    seconds. Five candidate causes were ruled out with direct measurement (Python GC, ORT's
    cuDNN algorithm search, cross-model GPU contention, submission-frequency throttling, an
    actual Windows/driver TDR reset) before concluding it was specific to that export -- the
    sibling BlazeFace model (same pipeline, same architecture family) never showed it. Switched
    to OpenCV Zoo's independent conversion of the same MediaPipe Hands architecture
    (`onnx_opencv_hands.py`, `data/ml/opencv_zoo/`) and the pathology disappeared completely (0
    outliers over a 3-minute/5000+-sample window), with `Effectivefps` also jumping from
    ~13-25 to 50-70+. See `docs/learnings/mediapipe-landmarks.md`'s "RESOLVED" section for the
    full investigation and the resolution. **Takeaway: if a specific ONNX export has a severe,
    hard-to-explain performance pathology that a same-architecture sibling model doesn't share,
    suspect the export itself before the runtime/driver/GPU-scheduling layer** -- trying an
    independently-converted alternative may be far cheaper than continuing to debug deeper.
  - The Qualcomm hand detector's anchor grid (2944 anchors, 256x256 input) did NOT match stock
    MediaPipe's own published `palm_detection_cpu.pbtxt` config (4-layer/2016-anchor/192x192) --
    reverse-derived by solving for a layer/stride combination whose anchor count matched exactly,
    then verified against real detections. OpenCV Zoo's export, by contrast, uses MediaPipe's
    exact STOCK anchor config (192x192, 4-layer, confirmed against OpenCV's own hardcoded
    2016-row anchor table) -- no reverse-engineering needed. If a future MediaPipe-family model
    doesn't match its own stock anchor config, use the same reverse-derivation approach: compute
    anchor counts for candidate stride/layer configs and match against the model's actual output
    shape, then verify with real detection scores (a correct config gives a tight cluster of
    near-identical high-confidence scores; a wrong one gives scattered near-random scores).
  - **Any new MediaPipe landmark model's x/y output units must be checked independently, every
    time -- there is no safe default to assume.** Qualcomm's `face_landmark_detector.onnx` /
    `hand_landmark_detector.onnx` output normalized 0-1 relative to the crop; OpenCV Zoo's
    `handpose_estimation_mediapipe_2023feb.onnx` outputs the OPPOSITE convention, already
    crop-space PIXELS. Same for input tensor LAYOUT: Qualcomm's exports are NCHW, OpenCV Zoo's
    are NHWC. Probe the raw `session.run()` output range (and check `get_inputs()[0].shape`) for
    a single real crop before trusting any inverse-affine math or preprocessing -- see
    `docs/learnings/mediapipe-landmarks.md` for the bug this caused the first time.
  - Debug-visualization landmark point clouds use a flat `table_landmarks` DAT (`track_id, lx,
    ly, lz`, one row per landmark across all tracked instances -- same convention as
    `onnx_yolo26_pose.py`'s `table_joints`), instanced directly via a `geometryCOMP`'s
    `instanceop` pointed straight at the Table DAT (no CHOP conversion needed -- confirmed
    working, see the learnings doc's "false lead" section).
  - `onnx_mediapipe_face.py` also derives head pose (yaw/pitch/roll, in degrees, appended as
    `table_output` columns) directly from 6 of its own already-computed 468 FaceMesh landmarks
    (nose tip, chin, eye corners, mouth corners) via `cv2.solvePnP` against a canonical 3D face
    model -- no extra model inference needed. Same data-output scheme (`Posemethod`/
    `Poseyawscale`/`Posepitchscale`/`Posefocalscale`/`Posesmoothing` pars, same column names) as
    the older `onnx_yunet.py`'s own head-pose implementation, but defaults to `solvepnp` rather
    than `geometric` (FaceMesh's 6 points span the whole face, unlike YuNet's 5 keypoints
    clustered in the eye/nose/mouth region, so the solve conditions much better here). No iris
    model is used, so only coarse head yaw/pitch is available, not true gaze/eye direction.
    Mouth/eye open-closed and eyebrow-raise signals are NOT yet implemented but would follow the
    same pattern -- simple distance ratios between existing FaceMesh landmark indices (MAR/EAR),
    no new model call needed either.