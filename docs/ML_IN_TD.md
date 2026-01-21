## ML in TD

Cuda versions for TD versions
- https://derivative.ca/UserGuide/CUDA

If you've installed pytorch:
```python
import torch
torch.version.cuda = '11.8'
torch.__version__ = '2.7.1+cu118'
```

TensorFlow:
- Can't run on GPU, but does work on CPU (Windows)

Pytorch:
- Noted incompatibilities, CUDA is difficult to recognize. Though TD does have CUDA in the TD /bin dir
  - What about a command like this? borrowed from facefusion
    - conda install conda-forge::cuda-runtime=12.8.0 conda-forge::cudnn=9.7.1.26
- Check these projects for torch example: 
  - https://github.com/TouchDesigner/TDDepthAnything
  - https://github.com/olegchomp/TDDepthAnything
  - https://github.com/patrickhartono/TDYolo
  - Related: https://huggingface.co/spaces/Xenova/webgpu-realtime-depth-estimation
- https://github.com/DBraun/PyTorchTOP
- https://forum.derivative.ca/t/import-pytorch-torch-in-build-2021-39010/245984/18

ONNX:
- Native onnx is supported but only if you're building a custom node w/C++: 
  - https://github.com/TouchDesigner/CustomOperatorSamples/tree/main/TOP/ONNXCandyStyleTOP
- Otherwise, you can use the onnxruntime-gpu python package to run onnx models in TD. Version 1.17 is GPU compatible!
  - https://onnxruntime.ai/docs/install/
  - `&"C:\Program Files\Derivative\TouchDesigner\bin\python.exe" -m pip install onnxruntime-gpu==1.17.0 --target="../_local_modules"`
  - `pip install onnxruntime-gpu --extra-index-url https://aiinfra.pkgs.visualstudio.com/PublicPackages/_packaging/onnxruntime-cuda-11/pypi/simple/`
- See the inner workings of an onnx model: https://netron.app/
- Try getting this running: https://github.com/fabio-sim/Depth-Anything-ONNX
- https://derivative.ca/community-post/real-time-magic-integrating-touchdesigner-and-onnx-models/69856
☝️ Check the comments
- https://github.com/IntentDev/TopArray/
- https://github.com/ioannismihailidis/venvBuilderTD/
- https://github.com/ioannismihailidis/madmomTD (edited)
- https://onnxruntime.ai/docs/tutorials/mobile/pose-detection.html
- https://docs.ultralytics.com/tasks/pose/
- https://docs.ultralytics.com/integrations/onnx/
- https://github.com/yeataro/TD-ONNX-EX
- Optical flow:
  - https://github.com/ibaiGorordo/ONNX-NeuFlowV2-Optical-Flow
  - https://github.com/ibaiGorordo/ONNX-RAFT-Optical-Flow-Estimation
- other ideas:
  - Human matting! https://github.com/PeterL1n/RobustVideoMatting
  - Find more models: 
  	- https://aihub.qualcomm.com/models
    - https://huggingface.co/qualcomm
    - https://huggingface.co/onnx-community/models
    - https://huggingface.co/onnxmodelzoo
  - hand tracking:
  	- https://github.com/PINTO0309/hand-gesture-recognition-using-onnx
  	- https://huggingface.co/qualcomm/MediaPipe-Hand-Detection/tree/main
  	- Ran into palm detection initial step issue
	- smollvm:
  	- https://huggingface.co/HuggingFaceTB/SmolVLM-256M-Instruct/discussions/4
	- openpose:
  	- https://docs.radxa.com/en/orion/o6/app-development/artificial-intelligence/openpose
  - onnx example in webgpu
    - https://medium.com/@geronimo7/in-browser-image-segmentation-with-segment-anything-model-2-c72680170d92
    - https://github.com/geronimi73/next-sam
	- SAM2
  	- https://github.com/ibaiGorordo/ONNX-SAM2-Segment-Anything
	- Alt pose estimation: https://github.com/Tau-J/rtmlib
- [bgnet segmentation](https://aihub.qualcomm.com/models/bgnet)
- [cavaface face analysis](https://aihub.qualcomm.com/models/cavaface)
- [controlnet-canny](https://aihub.qualcomm.com/models/controlnet_canny)
- [depth_anything_v2](https://aihub.qualcomm.com/models/depth_anything_v2)
- [easyocr - OCR](https://aihub.qualcomm.com/models/easyocr)
  - https://huggingface.co/monkt/paddleocr-onnx/tree/main
- [eyegaze](https://aihub.qualcomm.com/models/eyegaze)
- [foot_track_net - foot detection](https://aihub.qualcomm.com/models/foot_track_net)
- [lama_dilated - image inpainting](https://aihub.qualcomm.com/models/lama_dilated)
- [mediapipe_selfie - segmentation](https://aihub.qualcomm.com/models/mediapipe_selfie)
- PINTO!
  - https://github.com/PINTO0309/PINTO_model_zoo/tree/main/472_DEIMv2-Wholebody34
  - https://github.com/PINTO0309/PINTO_model_zoo/tree/main/333_E2Pose/demo
  - https://github.com/open-mmlab/mmpose/tree/main/projects/rtmpose
    - https://huggingface.co/qualcomm/RTMPose-Body2d/tree/main
  - https://github.com/PINTO0309/PINTO_model_zoo/tree/main/322_YOLOv7_Head
