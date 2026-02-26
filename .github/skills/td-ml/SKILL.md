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
& "C:\Program Files\Derivative\TouchDesigner\bin\python.exe" -m pip install onnxruntime-gpu==1.17.0 --target="../_local_modules"

# Or via pip with CUDA 11 index
pip install onnxruntime-gpu --extra-index-url https://aiinfra.pkgs.visualstudio.com/PublicPackages/_packaging/onnxruntime-cuda-11/pypi/simple/
```

Version 1.17 is confirmed GPU-compatible with TD.

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
| Pose estimation | [RTMPose](https://github.com/open-mmlab/mmpose/tree/main/projects/rtmpose), [rtmlib](https://github.com/Tau-J/rtmlib) |
| Hand tracking | [MediaPipe Hands](https://huggingface.co/qualcomm/MediaPipe-Hand-Detection/tree/main), [Hand Gesture Recognition](https://github.com/PINTO0309/hand-gesture-recognition-using-onnx) |
| Face analysis | [CavaFace](https://aihub.qualcomm.com/models/cavaface) |
| Eye gaze | [EyeGaze](https://aihub.qualcomm.com/models/eyegaze) |
| Object detection | [YOLOv7 Head](https://github.com/PINTO0309/PINTO_model_zoo/tree/main/322_YOLOv7_Head), [Wholebody](https://github.com/PINTO0309/PINTO_model_zoo/tree/main/472_DEIMv2-Wholebody34) |
| Optical flow | [NeuFlowV2](https://github.com/ibaiGorordo/ONNX-NeuFlowV2-Optical-Flow), [RAFT](https://github.com/ibaiGorordo/ONNX-RAFT-Optical-Flow-Estimation) |
| OCR | [EasyOCR](https://aihub.qualcomm.com/models/easyocr), [PaddleOCR ONNX](https://huggingface.co/monkt/paddleocr-onnx/tree/main) |
| Video matting | [RobustVideoMatting](https://github.com/PeterL1n/RobustVideoMatting) |
| Image inpainting | [LAMA Dilated](https://aihub.qualcomm.com/models/lama_dilated) |
| Foot detection | [FootTrackNet](https://aihub.qualcomm.com/models/foot_track_net) |

### TD-Specific ML Projects

- [TD-ONNX-EX](https://github.com/yeataro/TD-ONNX-EX)
- [TopArray](https://github.com/IntentDev/TopArray/)
- [venvBuilderTD](https://github.com/ioannismihailidis/venvBuilderTD/)
- [Real-Time ONNX in TD (tutorial)](https://derivative.ca/community-post/real-time-magic-integrating-touchdesigner-and-onnx-models/69856)

## Tips

- Always run inference on a **background thread** to avoid blocking TD's cook cycle
- Use `queue.Queue` to pass results back to the main thread (see [td-threading.md](td-threading.md))
- Match numpy version to what TD ships — incompatible versions crash `numpyArray()`
- Native ONNX via C++ custom operators is possible but requires building a custom plugin

## See Also

- [td-threading/SKILL.md](../td-threading/SKILL.md) — Background thread patterns
- [td-python-environment/SKILL.md](../td-python-environment/SKILL.md) — Installing packages, conda, venv
