---
name: td-python-environment
description: Environment setup for external Python modules in TouchDesigner. Use this when installing packages, configuring conda or venv, or managing sys.path.
---

# TouchDesigner Python Environment

How to use external Python modules, manage environments, and import code in TouchDesigner.

## Documentation

- [MOD Class](https://docs.derivative.ca/MOD_Class)
- [Python Classes and Modules](https://derivative.ca/UserGuide/Python_Classes_and_Modules)
- [tdPyEnvManager](https://docs.derivative.ca/Experimental:Palette:tdPyEnvManager)
- [External Python Libraries (Matt Ragan)](https://matthewragan.com/2019/09/04/touchdesigner-td-summit-2019-external-python-libraries/)

## Internal Modules (DAT as Module)

Import a Text DAT as a Python module using `mod`:

```python
# 4 equivalent ways to import a Text DAT named 'onnx_util'
import onnx_util
onnx_util = mod.onnx_util
onnx_util = mod('onnx_util')              # Can be a path too
onnx_util = mod(f'{op.PyUtils}/onnx_util')  # With a global op ref

# Grab a specific class from the module
ONNXManager = mod(f'{op.PyUtils}/onnx_inference_manager').ONNXInferenceManager
```

**Reload after changes:**
```python
import importlib
importlib.reload(module_to_reload)
```

Note: `mod.X` does not auto-reload when the source DAT changes. Use `importlib.reload()` during development or the experimental `op.TDModules` system.

## External Modules — tdPyEnvManager (Recommended)

The modern approach for managing third-party Python packages in TD:

- [Introducing tdPyEnvManager](https://derivative.ca/community-post/introducing-touchdesigner-python-environment-manager-tdpyenvmanager/72024)
- [TDPyEnvManagerHelper](https://docs.derivative.ca/Experimental:TDPyEnvManagerHelper)
- [Thread Manager Support](https://derivative.ca/community-post/custom-integration-thread-manager-support-third-party-python-library/72023)

## External Modules — Local Directory

Install packages into a local folder and add to `sys.path`:

```python
import sys
import os

module_path = os.path.join(project.folder, 'python', 'my_modules')
if module_path not in sys.path:
	if os.path.exists(module_path):
		sys.path.insert(0, module_path)
```

Install with TD's own Python for version compatibility:

```bash
# Windows — use TD's bundled Python
& "C:\Program Files\Derivative\TouchDesigner\bin\python.exe" -m pip install qrcode[pil] --target="./_modules"
```

Generate a requirements file with `pipreqs`:

```bash
pip install pipreqs
pipreqs /path/to/project --force
pipreqs . --ignore ".venv,numpy/core/tests" --force --encoding=iso-8859-1
```

## External Modules — Conda

Conda env **must match TD's Python version** (currently 3.11).

```bash
conda create -n td-project python=3.11
conda activate td-project

pip install -r requirements.txt

# Find env path for TD
conda env list

# Cleanup
conda deactivate
conda env remove -n td-project
```

**Gotcha:** If `top.numpyArray()` crashes, the conda env likely has an incompatible numpy version.

## External Modules — venv

```bash
python -m venv myenv
myenv\Scripts\activate        # Windows
pip install -r requirements.txt
```

## Custom Module Import Pattern

Full pattern for importing external `.py` files with reload support:

```python
import sys
import os
import importlib

module_path = os.path.join(project.folder, 'python', 'test_import')

if module_path not in sys.path:
	if os.path.exists(module_path):
		sys.path.insert(0, module_path)

import test_external
importlib.reload(test_external)  # Force reload during development

test_external.printSpecial()
```

## System / Environment Variables

```python
# Access TD system variables (set in Dialogs > Variables)
var("VAR_NAME")

# Add to PATH at runtime
import os
TOOL_PATH = r"C:\Program Files\MyTool"
if os.path.exists(TOOL_PATH):
	os.environ["PATH"] = TOOL_PATH + os.pathsep + os.environ["PATH"]
```

Set environment variables before TD starts using a shell launch script — see [Matt Ragan's guide](https://matthewragan.com/2019/08/05/touchdesigner-start-up-configuration-with-environment-variables/).

## TD Install Locations

Key paths inside the TD install directory:

```
TouchDesigner.2025.xxxxx\bin\Lib\tdi          # TD internal modules
TouchDesigner.2025.xxxxx\bin\Lib\tdutils      # TD utility modules
TouchDesigner.2025.xxxxx\bin\Lib\site-packages # Bundled Python packages
TouchDesigner.2025.xxxxx\Samples\Learn\        # Example projects
```

## See Also

- [.ai/skills/td-ml.md](.ai/skills/td-ml.md) — ML-specific environment setup (ONNX, PyTorch, CUDA)
- [.ai/skills/td-threading.md](.ai/skills/td-threading.md) — Threading with external libraries
- [.ai/skills/td-extension-template.md](.ai/skills/td-extension-template.md) — Extension class pattern
