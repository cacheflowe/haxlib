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

