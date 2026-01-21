## Advanced python coding in TD
Pattern matching
- https://docs.derivative.ca/Pattern_Matching

Native TD
- Python Extensions
- `import td` in an external script
- Basic Python intro: https://matthewragan.com/teaching-resources/touchdesigner/python-in-touchdesigner/
- https://github.com/raganmd/touchdesigner-process-managment
Subprocess:
- https://matthewragan.com/2019/08/14/touchdesigner-python-and-the-subprocess-module/
Windows extensions:
- https://github.com/mhammond/pywin32

Internal python modules for TD:
- https://docs.derivative.ca/MOD_Class

Example import of a Text DAT (named `onnx_util`) as a module, 4 equivalent ways:
```python
import onnx_util 
onnx_util = mod.onnx_util
onnx_util = mod('onnx_util') # this can be a path too
onnx_util = mod(f'{op.PyUtils}/onnx_util') # with a global op ref
onnx_util = op.PyUtils.Get('onnx_util') # need to reimport if source changes
ONNXInferenceManager = mod(f'{op.PyUtils}/onnx_inference_manager').ONNXInferenceManager # grab a class from the module
```

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

TD install locations of importance: 
- TouchDesigner.2025.32050\bin\Lib\tdi
- TouchDesigner.2025.32050\bin\Lib\tdutils
- TouchDesigner.2025.32050\Samples\Learn\OfflineHelp\https.docs.derivative.ca
- TouchDesigner.2025.32050\Samples\Learn\OPSnippets\Snippets
