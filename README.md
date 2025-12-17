# haxademic-td

A personal toolkit & demo playground

## TODO

- Save demos as tox files and get them out of the project
- Bring in components from Gatorade

## OOP in TD Concepts

- Base Comp or Container is a class
  - Customize w/parameters
  - Parexec
  - op()/ops() - query nodes like document.querySelector() in .js
  - Global op references are singletons or clone masters. Should only be at top level
- Cloning & replicators
  - Replilcator is like a for() loop that creates a bunch of objects from a class definition
  - Clones are like instances of a class, generally sprinkled throughout a project
- Externalizing .tox & .py files 
  - for git tracking & easy access in VS Code
  - externalized python is one step closer to normal AI-assisted dev workflows
- Python extensions
	- Class per comp/container
  	- Can handle lifecycle events
  	- execute dat traditionally handles some of this
  - Python -> nodes -> Python flow
    - Last node is a chopexec that calls back into the class
  - No floating chopexec scripts!
  - Logic in python, numeric operations in CHOPs
  - Dependable properties
  - /project1 gets an App extension w/global op ref
- Bootstrap App extension
  - .env vars
  - shell env vars
  - Launch app w/shell script, reliably
- External python modules - now w/ pyEnvManager
- Autosave w/dirty tox detection
- AppStore (w/socket server) - look at Zoox example
  - Store paths to shared nodes
- Refactoring
- Probably not for today
  - ML tools in TD
  - Threading

## GLSL in TD

From: https ://docs.derivative.ca/Write_a_GLSL_TOP

Built-in uniforms & functions:
```glsl
// Helpers
uniform sampler2D sTDNoiseMap;  // A 256x256 8-bit Red-only channel texture that has random data.
uniform sampler1D sTDSineLookup; // A Red-only texture that goes from 0 to 1 in a sine shape.

// Noise functions
float TDPerlinNoise(vec2 v);
float TDPerlinNoise(vec3 v);
float TDPerlinNoise(vec4 v);
float TDSimplexNoise(vec2 v);
float TDSimplexNoise(vec3 v);
float TDSimplexNoise(vec4 v);

// Information about the textures
TDTexInfo uTDOutputInfo; // The current texture context
TDTexInfo uTD2DInfos[]; // only exists if inputs are connected 

// Converts between RGB and HSV color space
vec3 TDHSVToRGB(vec3 c);
vec3 TDRGBToHSV(vec3 c);

// Applies a small random noise to the color to help avoid banding in some cases.
vec4 TDDither(vec4 color);
```

Extras:
```glsl
#define PI     3.14159265358
#define TWO_PI 6.28318530718
```

Correct aspect ratio: 
```glsl
float width = 1./uTDOutputInfo.res.z;
float height = 1./uTDOutputInfo.res.w;
vec2 aspect = width * uTDOutputInfo.res.wz; // swizzle height/width
vec2 p = vUV.xy / aspect;
```

Center the coordinate system
```glsl
vec2 p = (vUV.st - vec2(0.5)) / aspect;
```

## run()

[run()](https://derivative.ca/UserGuide/Run_Command_Examples)

```python
# Call a class function with a delay in an extension
run(lambda: self.BroadcastVals(), delayFrames=30)
run(self.BroadcastVals, delayFrames=30)
run('self.BroadcastVals(args)', delayFrames=30)
run( "args[0]()", lambda: self.update_par("dos"), delayFrames = 200 )  # https://forum.derivative.ca/t/using-run-to-delay-python-code-2022-12-11-15-37/306405/2
# Call a global function with a delay
run("broadcastVals()", delayFrames=30)
# Call a function with an argument
run("TurnOff(args[0])", oldConnection, delayFrames=30)
# Call a script DAT with an argument and a delay
op('text_script_example').run('arg1=something', delayFrames=30)
```


run() w/delay from extension

```python
run("parent().SampleTriggerOff()", fromOP=me, delayFrames=1)
run(f"op('{self.ownerComp.path}').PulseTriggerLaunch()", delayFrames=delayFrames)
```

## Call a function from another text DAT

```python
op('text_other_script').module.function_name()
op('text_other_script').run('function_name()')	
op('text_other_script').run('function_name(args)', delayFrames=30)
op('text_other_script').run('function_name(args)', delayFrames=30, fromOP=me)
op('text_other_script').run('function_name(args)', delayFrames=30, fromOP=me, args=[arg1, arg2])
```

## Threading examples

Threading in action:
- JoystickToMouse.tox
- PythonWebServer.tox
- AppStore start webserver cmd 


Threading:
```python
import queue
import threading
import os

class PythonWebServer:
	def __init__(self, ownerComp):
		self.status_queue = queue.Queue() 

	def StartServer(self):
		self.thread = threading.Thread(target=self.StartServerThread)
		self.thread.daemon = True  # Set as daemon thread
		self.thread.start()

	def CheckServerActive(self):
		"""Callback function is executed on the main thread, called by DAT execute every frame."""
		try:
				result = self.status_queue.get(block=False) # non-blocking get
				# print("Result received: {}".format(result))
				self.is_active = result[0]
		except queue.Empty:
				pass # queue is empty nothing to do.
		return
	
	def SetActiveStatus(self, active):
		self.status_queue.put(active)

	def StopServer(self):
		if self.httpd is None:
			print('[PythonWebServer] No server to stop!')
			self.SetActiveStatus([False, 'Stopped'])
			return

		self.stopThread = threading.Thread(target=self.StopServerThread)
		self.stopThread.start()
		# run("parent().SetActive(0)", fromOP=me, delayFrames=1)

	def StopServerThread(self):
		# clean up
		self.thread.join()
		self.shutdown_event.set()
		# self.stopThread.join()
```

String formatting

```python
# quick string interpolation
f'var = {variable}'
'var = {}'.format(variable) # alt
# zero padding a number
'{:03d}'.format(1) # 001
'{:010d}'.format(9223) # 0000009223
# zero pad a string
'hi'.zfill(10) # 0000000hi
'hi'.rjust(10, '0') # 0000000hi
# rounding numbers
f'{variable:.2f}' # 2 decimal places
f'{variable:.0f}' # no decimal places
# rounding with padding
f'{variable:05.2f}' # 5 total spaces, 2 decimal places
```

## Advanced python coding in TD

Native TD
- Python Extensions
- `import td` in an external script
- Basic Python intro: https://matthewragan.com/teaching-resources/touchdesigner/python-in-touchdesigner/
- https://github.com/raganmd/touchdesigner-process-managment
Subprocess:
- https://matthewragan.com/2019/08/14/touchdesigner-python-and-the-subprocess-module/
Windows extensions:
- https://github.com/mhammond/pywin32

External module support (NEW)
- tdPyEnvManager:
  - https://derivative.ca/community-post/introducing-touchdesigner-python-environment-manager-tdpyenvmanager/72024
  - https://docs.derivative.ca/Experimental:TDPyEnvManagerHelper
  - https://docs.derivative.ca/Experimental:Palette:tdPyEnvManager
  - https://derivative.ca/community-post/custom-integration-thread-manager-support-third-party-python-library/72023

External module support
- Importing local custom modules w/sys.path
- Via `Conda`: https://derivative.ca/community-post/tutorial/anaconda-miniconda-managing-python-environments-and-3rd-party-libraries
- Via `venv`: https://forum.derivative.ca/t/real-time-magic-integrating-touchdesigner-and-onnx-models-2024-07-24/503693/5
  - https://github.com/olegchomp/TDDepthAnything
- Via `uv`: https://github.com/astral-sh/uv
- Via `TD_PIP` component (Window's only): https://derivative.ca/community-post/asset/td-pip/63077
- https://github.com/PlusPlusOneGmbH/TD_PyPaIn
- Matthew Ragan's talk on external modules: https://matthewragan.com/2019/09/04/touchdesigner-td-summit-2019-external-python-libraries/
	- python -m pip install --user --upgrade pip
	- pip install -r "{reqs}" --target="{target}"
	- pip install qrcode[pil] --target="{target}"
	- Then add in python script in TD:
		```python
		import sys
		import os
		sys.addpath(target)
		```
	- Maybe use TD's python to install, for compatibility? Also can use a matching Conda env
  	- `&"C:\Program Files\Derivative\TouchDesigner\bin\python.exe" -m pip install qrcode[pil] --target="./_modules"`\

Using system variables
- Set system vars before startup from shell script: https://www.youtube.com/watch?v=0RNqVlaW8Fo
- Dialogs > Variables shows system variables
  - var("VAR_NAME") to access them in TD via Python
- Start TD files via python vs shell script: https://www.youtube.com/watch?v=UxvJG0Iqg1Q

Adding system variables on the fly to simulate having an environent variable:
```python	
import os
# Add Nmap to PATH, but first check whether it exists on the actual system filepath
NMAP_PATH = r"C:\Program Files (x86)\Nmap"
if os.path.exists(NMAP_PATH):
    os.environ["PATH"] = NMAP_PATH + os.pathsep + os.environ["PATH"]
    print(f"Added Nmap directory to PATH: {NMAP_PATH}")
else:
    print(f"Warning: Nmap directory not found at {NMAP_PATH}")
```

## Python dependencies info

Python extension help:
- https://derivative.ca/community-post/tutorial/tdudependency-tutorial/66489
- https://derivative.ca/UserGuide/Dependency_Class
  - `self.Scale = tdu.Dependency(5)`
  - For objects (not single values), use Deeply dependable objects
    - https://derivative.ca/UserGuide/TDStoreTools#Deeply_Dependable_Collections
- https://derivative.ca/UserGuide/CallbacksExt_Extension
- https://derivative.ca/UserGuide/Extensions
- https://derivative.ca/UserGuide/Talk:Extensions
  - `__delTD__` is the pre-experimental way to cleanup a class when it's been re-saved
- https://derivative.ca/UserGuide/Experimental:Extensions
  - `onDestroyTD` for cleanup of listeners!
  - use `StorageManager` to keep values between saves, because init() resets everything
  - `TDF.createProperty` makes a variable dependable
- https://derivative.ca/UserGuide/Introduction_to_Python_Tutorial
  - `mod` for one-line imports
  - `op.TDModules`
- https://docs.derivative.ca/TDFunctions

General:
- https://derivative.ca/UserGuide/Category:TDPages
- https://derivative.ca/UserGuide/Python_Classes_and_Modules
- https://derivative.ca/UserGuide/Python_Tips (general .py goodness)
- https://docs.derivative.ca/Introduction_to_Python_Tutorial
- https://derivative.ca/UserGuide/Working_with_OPs_in_Python
- https://derivative.ca/UserGuide/Using_Multiple_Graphic_Cards
- https://docs.derivative.ca/OpenCV

Classes of interest
- https://derivative.ca/UserGuide/Project_Class
- https://derivative.ca/UserGuide/App_Class
- https://derivative.ca/UserGuide/Color_Class

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

## Local modules

- You can install python modules in a local directory, and then add that directory to the python path in TD.
- This allows you to use custom modules in your TD project without installing them globally.
- By installing with the TouchDesigner python, you ensure compatibility with the TD version.
- Use `pipreqs` to generate a version-specific requirements.txt file for your local modules:
```bash
pip install pipreqs
pipreqs /path/to/your/project --force
pipreqs . --ignore ".venv,numpy/core/tests,pyparsing" --force --encoding=iso-8859-1
```

## Conda env

From: https://derivative.ca/community-post/tutorial/anaconda-miniconda-managing-python-environments-and-3rd-party-libraries

Notes:
- Conda env needs to use the same python version as TouchDesigner. Currently 3.11
- Conda installs its own version of Python
- If top.numpyArray() breaks, something's wrong with the conda env. Upcoming TD versions claim to have a fix for these hard crashes

```bash
conda env list
conda create -n td-demo python=3.11
conda activate td-demo

# install the requirements.txt file
conda install --yes --file requirements.txt
pip install -r requirements.txt

# Check version of TD libs and make sure you're using compatible versions of numpy, for example
import numpy
print(numpy.__version__)

# install some libs
pip install numpy==1.24.4 # 1.24.4 is the last version that works with TD 2023.30000
# [pytesseract]
conda install -c conda-forge pytesseract
# choco install tesseract
conda install -c conda-forge pillow
# epson priner
pip install python-escpos
# ultralytics (needs numpy 1.24.1)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
pip install ultralytics
pip install onnxruntime-gpu

# find the path to the conda env
conda env list
# or
conda info --envs

# remove the env
conda deactivate
conda env remove -n td-demo

# Export the env to a requirements.txt file
conda list -e > requirements.txt
# or maybe
conda env export --name td-demo > requirements.txt
```

## venv

```bash
# Create a virtual environment in a local folder
# Make sure you have python installed and available in your PATH
python -m venv myenv

# Activate the virtual environment
# On Windows
myenv\Scripts\activate

# Install packages
pip install -r requirements.txt
```

## Import a custom python module

```python
import sys
import os
import importlib

# Set up external module script
# - Create dir at ./python/test_import
# - Create empty __init__.py file in the test_import folder
# - Create test_external.py file in the test_import folder with a function printSpecial()

# Construct the path to the TD project's directory containing test_external.py
module_path = os.path.join(project.folder, 'python', 'test_import')

# check path for new module_path in os.path
# and check if the module path is already in sys.path and that it's a valid location
if module_path not in sys.path:
  if os.path.exists(module_path): # If not, add it to sys.path
    sys.path.insert(0, module_path)  # Add to the beginning of the path list
    # print paths as bulletpoints
    print("Python path updated:")
    for path in sys.path:
      print("- ", path)

# Now you can import from test_external.py
# Reload the module in case it's code has changed. It gets cached when imported. You can remove importlib once stable.
import test_external
importlib.reload(test_external)

# Call the function from test_external.py
test_external.printSpecial()
```

Reload module if the source .py file has changed:

```python
import importlib
importlib.reload(module_to_reload)
```


## Replicator template snippets

Anchor replicants to the replicator parent by setting the Layout Origin props

```python
me.nodeX + 300
me.nodeY
```

```python
def onReplicate(comp, allOps, newOps, template, master):
	# get mixer & layout operators
	opDest = parent().op('merge1')

	for c in newOps:
		# set props to enable from disabled template
		c.par.display = 1
		c.par.enable = 1
		# connect to destination
		c.outputConnectors[0].connect(opDest)
		pass

	return
```


## Script OPs

Create or reuse a channel:

```python
if scriptOp['test1'] is None:
	scriptOp.appendChan('test1')
scriptOp['test1'][0] = 0.777
```


## For loops

```python
for i in range(10):
for i in range(maxResults):
for detection in detection_result.detections:
for i, detection in enumerate(detection_result.detections):
for i in range(min(maxResults, len(detection_result.detections))):
for i, c in enumerate(newOps): # replicator
```

## Concat a table DAT into a single line

```python
"\n".join([f"{row[0]}: {row[1]}" for row in op('eval_props').rows()])
```

## Op connectors

```python
op.inputs[0]
op1.outputConnectors[0].connect(op2)
op1.outputConnectors[0].connect(op2.inputConnectors[0])
```


## Get text width

```python
me.evalTextSize(me.par.text.eval())[0]
op('text_top').evalTextSize("text to measure")[0]
```

## Debugging

```python
debug(variable) # TouchDesigner debug print - provides more info than print()
dir(newTuplet) # list all properties & methods of an object
print(repr(variable)) # detailed representation of a variable	
print(type(variable)) # type of variable
```

## Extension template

```python
from TDStoreTools import StorageManager
import TDFunctions as TDF
import tdu

class NewExtension:
	"""
	NewExtension description
	"""

	def __init__(self, ownerComp):
		self.ownerComp = ownerComp
		# Create dependable properties that reset when extension is saved
		TDF.createProperty(self, 'MyProp1', value=3, dependable=True, readOnly=False) 
		self.MyProp2 = tdu.Dependency(3)

		# Example update different dependable props:
		# self.MyProp1 = 11
		# self.MyProp2.val = 5

		# Create dependables with StorageManager, which persist between saves
		self.stored = StorageManager(self, ownerComp, [
			{'name': 'ExampleProp', 'default': 13, 'readOnly': False, 'property': True, 'dependable': True},
		])
		self.ExampleProp = 14

	def Reset(self):
		return

	# AppStoreToggle callbacks

	def On_show(self):
		self.Reset()  

	def On_hidden(self):
		self.Reset()

	# Extension cleanup methods (new and old versions of TD)

	def __delTD__(self):
		self.dispose()

	def onDestroyTD(self):
		self.dispose()

	def __del__(self):
		# called after onDestroyTD
		return
		
	def dispose(self):
		print('[NewExtension] Cleaning up')
		# self.stored.clear() # Uncomment to reset stored values

```


## Run a shell script on a thread

```python
# https://docs.python.org/3/library/subprocess.html#subprocess.Popen

import threading
import subprocess
from subprocess import Popen, PIPE, STDOUT
import system_util

def run_script():
    # Start the subprocess and specify stdout and stderr to be piped
    p = Popen(['serve-all.cmd'], cwd='www\\scripts', stdout=PIPE, stderr=STDOUT, shell=True, text=True, bufsize=1)

    # Use a loop to read the output line by line as it becomes available
    for line in p.stdout:
      print(line, end='')  # Print each line of the output

    p.stdout.close()  # Close the stdout stream
    p.wait()  # Wait for the subprocess to exit

# Create and start a thread to run the run_script function
thread = threading.Thread(target=run_script)
thread.start()

# open a browser window at current ip address
# get ip address
ipAddr = system_util.get_ip_address()
system_util.open_url("http://" + ipAddr + ":5173/app-store-distributed/index.html")
```