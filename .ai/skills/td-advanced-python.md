---
name: td-advanced-python
description: Advanced Python in TouchDesigner — external modules (conda/venv/uv/tdPyEnvManager), subprocess, MOD class imports, system variables, pattern matching, and pywin32. Use when setting up external libraries or advanced Python integration.
---

# Advanced Python in TouchDesigner

## Pattern Matching

- https://docs.derivative.ca/Pattern_Matching

## Native TD Python

- Python Extensions
- `import td` in an external script
- Basic Python intro: https://matthewragan.com/teaching-resources/touchdesigner/python-in-touchdesigner/
- https://github.com/raganmd/touchdesigner-process-managment

## Subprocess

- https://matthewragan.com/2019/08/14/touchdesigner-python-and-the-subprocess-module/

## Windows Extensions

- https://github.com/mhammond/pywin32

## Internal Python Modules (MOD Class)

- https://docs.derivative.ca/MOD_Class
- https://medium.com/partical.grt/local-variables-modules-and-storage-touch-touchdesigner-tip-4-320bc6ba14c

## Parameters and Storage

- https://docs.derivative.ca/Internal_Parameters#Pros_and_Cons_of_Internal_Parameters

## Importing a Text DAT as a Module

Four equivalent ways to import a Text DAT named `onnx_util`:

```python
import onnx_util
onnx_util = mod.onnx_util
onnx_util = mod('onnx_util')                      # can be a path too
onnx_util = mod(f'{op.PyUtils}/onnx_util')        # [deprecated] with a global op ref
onnx_util = op.PyUtils.Get('onnx_util')           # [deprecated] need to reimport if source changes
ONNXInferenceManager = mod(f'{op.PyUtils}/onnx_inference_manager').ONNXInferenceManager # [deprecated]
```

## External Module Support

### tdPyEnvManager (recommended)

- https://derivative.ca/community-post/introducing-touchdesigner-python-environment-manager-tdpyenvmanager/72024
- https://docs.derivative.ca/Experimental:TDPyEnvManagerHelper
- https://docs.derivative.ca/Experimental:Palette:tdPyEnvManager
- https://derivative.ca/community-post/custom-integration-thread-manager-support-third-party-python-library/72023

### sys.path approach

```python
import sys
import os
target = "./_modules"
sys.path.insert(0, target)
# Install packages to the target folder:
# & "C:\Program Files\Derivative\TouchDesigner\bin\python.exe" -m pip install qrcode[pil] --target="./_modules"
```

### Via Conda

- https://derivative.ca/community-post/tutorial/anaconda-miniconda-managing-python-environments-and-3rd-party-libraries

### Via venv

- https://forum.derivative.ca/t/real-time-magic-integrating-touchdesigner-and-onnx-models-2024-07-24/503693/5
- https://github.com/olegchomp/TDDepthAnything

### Via uv

- https://github.com/astral-sh/uv

### Via TD_PIP (Windows only)

- https://derivative.ca/community-post/asset/td-pip/63077
- https://github.com/PlusPlusOneGmbH/TD_PyPaIn

### Matthew Ragan's external module talk

https://matthewragan.com/2019/09/04/touchdesigner-td-summit-2019-external-python-libraries/

```bash
python -m pip install --user --upgrade pip
pip install -r "{reqs}" --target="{target}"
pip install qrcode[pil] --target="{target}"
# Use TD's Python for compatibility:
& "C:\Program Files\Derivative\TouchDesigner\bin\python.exe" -m pip install qrcode[pil] --target="./_modules"
```

## System Variables

Set system vars before TD starts from a shell script: https://www.youtube.com/watch?v=0RNqVlaW8Fo

Dialogs > Variables shows system variables. Access in Python: `var("VAR_NAME")`

Start TD files via shell script: https://www.youtube.com/watch?v=UxvJG0Iqg1Q

### Adding env vars at runtime

```python
import os
NMAP_PATH = r"C:\Program Files (x86)\Nmap"
if os.path.exists(NMAP_PATH):
    os.environ["PATH"] = NMAP_PATH + os.pathsep + os.environ["PATH"]
    print(f"Added Nmap directory to PATH: {NMAP_PATH}")
else:
    print(f"Warning: Nmap directory not found at {NMAP_PATH}")
```

## Python Dependency Resources

- https://derivative.ca/community-post/tutorial/tdudependency-tutorial/66489
- https://derivative.ca/UserGuide/Dependency_Class
  - `self.Scale = tdu.Dependency(5)`
  - For objects (not single values), use Deeply dependable objects: https://derivative.ca/UserGuide/TDStoreTools#Deeply_Dependable_Collections
- https://derivative.ca/UserGuide/CallbacksExt_Extension
- https://derivative.ca/UserGuide/Extensions
- `onDestroyTD` for cleanup of listeners (experimental extensions)
- Use `StorageManager` to keep values between saves, because `init()` resets everything
- `TDF.createProperty` makes a variable dependable
- https://derivative.ca/UserGuide/Introduction_to_Python_Tutorial
- https://docs.derivative.ca/TDFunctions

## General Python Resources

- https://derivative.ca/UserGuide/Category:TDPages
- https://derivative.ca/UserGuide/Python_Classes_and_Modules
- https://derivative.ca/UserGuide/Python_Tips
- https://derivative.ca/UserGuide/Working_with_OPs_in_Python

## TD Install Locations

```
TouchDesigner.2025.32050\bin\Lib\tdi
TouchDesigner.2025.32050\bin\Lib\tdutils
TouchDesigner.2025.32050\Samples\Learn\OfflineHelp\https.docs.derivative.ca
TouchDesigner.2025.32050\Samples\Learn\OPSnippets\Snippets
```

## See Also

- [.ai/skills/td-python-environment.md](.ai/skills/td-python-environment.md) — tdPyEnvManager, DAT-as-module imports, TD install paths
- [.ai/skills/td-python-patterns.md](.ai/skills/td-python-patterns.md) — operator patterns, parameters, storage
