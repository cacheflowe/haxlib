# VS Code Python Setup for TouchDesigner

---

## Vanilla project (no haxlib)

Point VS Code directly at TD's Python interpreter. This gives you Pylance autocomplete and type hints for all built-in TD objects via the `tdi` stubs.

`.vscode/settings.json`:
```json
{
  "python.defaultInterpreterPath": "C:/Program Files/Derivative/TouchDesigner/bin/python.exe"
}
```

No venv, no extra steps. TD's Python is the interpreter so all TD-shipped packages (cv2, numpy, etc.) resolve automatically.

---

## Full setup — haxlib / TDPyEnvManager

### First-time project setup steps

1. **Add modules in requirements.txt** at the project root (`/requirements.txt`)
2. **Add the TDPyEnvManager COMP** to your TD project
3. **Set Environment Name** to `.venv`
4. **Click "Create From Requirements.txt"** — TD creates `.venv` based on its own Python 3.11 and installs your dependencies
5. **Configure `.vscode/settings.json`** — point to `.venv` as the interpreter (this interpreter resolves modules installed from requirements.txt), and add TD's paths for Pylance to resolve TD-shipped packages and TD type stubs. Also add your local module paths so Pylance can resolve those imports in VS Code:

```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/Scripts/python.exe",
  "python.analysis.extraPaths": [
    "${workspaceFolder}/python",
    "${workspaceFolder}/python/util",
    "${workspaceFolder}/python/extensions",
    "${workspaceFolder}/python/net",
    "C:/Program Files/Derivative/TouchDesigner/bin/Lib/site-packages",
    "C:/Program Files/Derivative/TouchDesigner/bin/Lib",
    "C:/Program Files/Derivative/TouchDesigner/bin/Lib/tdi"
  ]
}
```

5. **Add local module paths to `TDPyEnvManagerContext.yaml`** — the TDPyEnvManager COMP reads this on boot and adds the paths to `sys.path`, making local modules importable in TD without manually touching `sys.path` in custom code:

```yaml
extraPaths:
  - python
  - python/util
  - python/extensions
  - python/net
```

6. **Use `td.reloadModules()`** during development to refresh cached local modules after edits (see below)

---

### What each VS Code extraPath does

| Path | Provides |
|------|----------|
| `Lib/site-packages` | Third-party packages TD ships (cv2, numpy, etc.) |
| `Lib` | TD helpers: `TDFunctions`, `TDJSON`, `TDStoreTools` |
| `Lib/tdi` | TD type stubs: `op()`, `me`, `absTime`, `tableDAT`, etc. |

---

### extraPaths in TDPyEnvManagerContext.yaml vs settings.json

These look the same but serve entirely different systems — both are required:

- **`TDPyEnvManagerContext.yaml` `extraPaths`** — tells the TDPyEnvManager COMP what to add to `sys.path` at TD runtime. Requires the TDPyEnvManager COMP to be present and active in the `.toe`.
- **`settings.json` `python.analysis.extraPaths`** — tells Pylance (VS Code static analysis) where to find imports for type resolution and autocomplete. Neither knows about the other.

If you don't have the TDPyEnvManager COMP, register paths manually in `Bootstrap.py` instead:

```python
def loadPythonModules(self):
    for subdir in ['python', 'python/util', 'python/extensions', 'python/net']:
        config.AddPyDirToPath(os.path.join(project.folder, subdir))
```

---

## Using local modules inside TD

### Python textport / console

Since the module paths are on `sys.path`, use standard Python import. Once imported the module stays cached in `sys.modules` until TD restarts or you reload.

```python
# import and call in one line
import td_util; td_util.get_node_color(op('myNode'))

# pull a function directly into scope
from penner import easeInOutQuad; easeInOutQuad(0.5)

# subsequent calls in the same session don't need the import
td_util.set_node_color(op('myNode'), 1, 0, 0)
```

Note: `mod('td_util')` won't work here — `mod()` is only for modules stored as Text DATs in the TD network, not file-based modules.

### Node parameter expressions

Parameter expressions must be a single expression (no semicolons), so use `__import__`:

```python
__import__('td_util').get_node_color(me)
```

If the module is already imported (e.g. after `td.reloadModules()` has run), you can also reference it directly via `sys.modules`:

```python
sys.modules['td_util'].get_node_color(me)
```

---

## Reloading modules at runtime

TD caches imported modules, so edits to `.py` files don't take effect until the module is reloaded. The Bootstrap extension exposes `td.reloadModules()` globally for this.

From the TD textport or any script:
```python
td.reloadModules()
```

reloadModules source:

```python
def reloadModules(self):
  import glob
  import td
  tdTypes = {k: v for k, v in vars(td).items() if not k.startswith('_')}
  reloaded = []
  skipped = []
  subdirs = ['python', 'python/util', 'python/extensions', 'python/net']
  for subdir in subdirs:
    for filepath in glob.glob(os.path.join(project.folder, subdir, '*.py')):
      modName = os.path.splitext(os.path.basename(filepath))[0]
      if modName.startswith('_') or modName == 'Bootstrap':
        continue
      try:
        if modName in sys.modules:
          sys.modules[modName].__dict__.update(tdTypes)
          importlib.reload(sys.modules[modName])
          reloaded.append(modName)
        else:
          importlib.import_module(modName)
          reloaded.append(modName)
      except ModuleNotFoundError:
        skipped.append(modName)
      except Exception:
        skipped.append(modName)
  print(f'[Bootstrap] Reloaded: {reloaded}')
  if skipped:
    print(f'[Bootstrap] Skipped: {skipped}')
```

Add to the global `td` namespace on boot so it's always available without import.

```python
import td
td.reloadModules = self.reloadModules
```

### How it works

`reloadModules()` scans the project's Python subdirectories, then for each `.py` file either reloads it (if already in `sys.modules`) or imports it fresh. Before reloading, it injects TD's type namespace into the module so that type annotations using TD types (`tableDAT`, `containerCOMP`, etc.) don't cause `NameError`.

### Why TD types cause errors during reload

Python evaluates type annotations eagerly at import time. Annotations like `def fn(table: tableDAT)` look up `tableDAT` as a name when the function is defined. TD normally injects its type names as builtins into script execution contexts, but `importlib.reload()` re-executes the module in its own isolated namespace where those types aren't present. Pre-injecting `vars(td)` into the module before reloading solves this without touching the source file.

### What gets skipped

- `Bootstrap.py` itself (the running extension)
- Modules with missing optional dependencies (`ModuleNotFoundError`)
- TD extension files that have TD API calls at module level (e.g. `App.py`)

## More Reading/Watching:

- [A little about Modules, Locals, and Storage by Matthew Ragan](https://www.youtube.com/watch?v=B_awPnzhAMQ)