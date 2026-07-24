---
name: td-vscode-python-environment
description: Use when configuring VS Code, Pylance, or virtual environments for TouchDesigner Python projects.
---

# VS Code Python Setup for TouchDesigner

---

## Vanilla project (no haxlib or TDPyEnvManager)

Point VS Code directly at TD's Python interpreter. This gives you Pylance autocomplete and type hints for all built-in TD objects via the `tdi` stubs. This uses the 2025 addition of [TDI_Library](https://derivative.ca/UserGuide/TDI_Library) in TouchDesigner.

`.vscode/settings.json`:
```json
{
  "python.defaultInterpreterPath": "C:/Program Files/Derivative/TouchDesigner/bin/python.exe",
  "editor.insertSpaces": false,
  "editor.tabSize": 4
}
```

No venv, no extra steps. TD's Python is the interpreter so all TD-shipped packages (cv2, numpy, etc.) resolve automatically.

---

## Full setup — haxlib / TDPyEnvManager

Using [tdPyEnvManager](https://derivative.ca/UserGuide/Palette:tdPyEnvManager) and the [TDPyEnvManagerHelper](https://derivative.ca/UserGuide/TDPyEnvManagerHelper) class, you can also set up a more advanced Python development environment with virtual environments, allowing you to manage dependencies and keep your development environment organized. This is especially useful if you're working on multiple TD projects or developing libraries that have their own dependencies.


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
    "${workspaceFolder}/python/stubs",
    "${workspaceFolder}/python/app",
    "${workspaceFolder}/python/scripts",
    "${workspaceFolder}/python/util",
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
  - python/app
  - python/scripts
  - python/util
  - python/net
```

1. **Use `td.reloadModules()`** during development to refresh cached local modules after edits (see below)

---

### What each VS Code extraPath does

| Path | Provides |
|------|----------|
| `python/stubs` | Hand-written stubs for TD C extension built-ins (see below) |
| `Lib/site-packages` | Third-party packages TD ships (cv2, numpy, etc.) |
| `Lib` | TD helpers: `TDFunctions`, `TDJSON`, `TDStoreTools` |
| `Lib/tdi` | TD type stubs: `op()`, `me`, `absTime`, `tableDAT`, etc. |

#### TD C extension built-ins (tdu, etc.)

Some TD modules like `tdu` are C extensions loaded directly into TD's process at runtime — no `.py` file exists on disk for Pylance to introspect, even when pointing at TD's own Python interpreter. TD ships a stub for `td` at `Lib/tdi/td.py`, but not for `tdu`.

The fix is a hand-written stub at `python/stubs/tdu.py`. This path is in `extraPaths` (Pylance only) but intentionally **not** in `TDPyEnvManagerContext.yaml`, so the stub never shadows TD's real built-in at runtime.

---

### extraPaths in TDPyEnvManagerContext.yaml vs settings.json

These look the same but serve entirely different systems — both are required:

- **`TDPyEnvManagerContext.yaml` `extraPaths`** — tells the TDPyEnvManager COMP what to add to `sys.path` at TD runtime. Requires the TDPyEnvManager COMP to be present and active in the `.toe`.
- **`settings.json` `python.analysis.extraPaths`** — tells Pylance (VS Code static analysis) where to find imports for type resolution and autocomplete. Neither knows about the other.

If you don't have the TDPyEnvManager COMP, register paths manually in `Bootstrap.py` instead:

```python
def loadPythonModules(self):
    for subdir in ['python', 'python/util', 'python/app', 'python/net']:
        config.AddPyDirToPath(os.path.join(project.folder, subdir))
```

---

### Project architecture: App as the entry point

This project uses a single top-level `App` extension attached to the `/project` COMP. `App` is the first user-defined code that runs and is responsible for bootstrapping everything else — loading the AppStore file, applying defaults, registering singletons, and setting initial state.

Other global extensions (`AppStore`, `Colors`, etc.) live as child COMPs of `/project`. TD initializes child COMPs before the parent, so by the time `App.__init__` runs, all child extensions are already initialized and accessible via `op.X.ext.X`.

This architecture is what makes `RegisterSingletons()` work reliably — it runs at the top of `App.__init__` and can safely reach all child extensions. The initialization timing issues explored below are specific to this setup: a top-level orchestrator extension that boots after its dependencies.

---

### Autocomplete for op.ExtensionName references

`op.AppStore`, `op.Colors`, etc. return `baseCOMP` — Pylance has no way to know the actual extension type.

#### Singleton reference (recommended for most code)

Add `i: ClassVar[AppStore] = None` to the extension class and set it in `__init__`. `from __future__ import annotations` is required so the forward reference to `AppStore` inside the class body resolves correctly.

```python
from __future__ import annotations
from typing import ClassVar

class AppStore:
    i: ClassVar[AppStore] = None  # type: ignore  # singleton, set in __init__

    def __init__(self, ownerComp: baseCOMP) -> None:
        AppStore.i = self  # set on every TD init/reinit
        ...
```

Any file that imports the class can then access the live instance with full autocomplete:

```python
from AppStore import AppStore

AppStore.i.GetString('key')   # fully typed
AppStore.i.SetFloat('key', 1) # fully typed
```

**Initialization caveat:** `AppStore.i` is `None` until `AppStore.__init__` runs. For most extensions this is fine — by the time their code executes, AppStore is already initialized. But the top-level `App` extension initializes *alongside* AppStore and cannot rely on `AppStore.i` being set during its own `__init__`.

#### Typed property (for App and other top-level orchestrators)

`op.AppStore` is resolved lazily by TD's runtime on every call, so it always reflects the current initialized state regardless of init order. A `@property` wrapper preserves this guarantee while adding type information:

```python
from AppStore import AppStore

class App:
    @property
    def AppStore(self) -> AppStore:
        return op.AppStore  # TD guarantees resolution after network init

    def Bootstrap(self):
        self.AppStore.LoadFile()  # safe even during App.__init__
```

Use the `@property` approach in `App.py` (or any extension that boots alongside its dependencies). Use `AppStore.i` everywhere else.

**Note:** do not move the `@property` accessor into AppStore.py as a classmethod. File-based modules loaded via `sys.path` don't have the same TD builtin injection as extension scripts, so `op` may not be available there.

#### Bridging the singleton into sys.modules

TD loads extensions in its own execution context, separate from Python's import system. This means `AppStore.i` set during TD's extension init lives on a different class object than the one you get when doing `from AppStore import AppStore` in a DAT script. The two contexts don't share state by default.

The fix is `App.RegisterSingletons()`, called at the top of `App.__init__`. It explicitly bridges every global singleton into `sys.modules` using `op.X.ext.X` (which resolves the live TD extension instance) and `config.register_singleton` (which sets `.i` on the cached module class):

```python
def RegisterSingletons(self) -> None:
    App.i = config.register_singleton(self, 'App')
    AppStore.i = config.register_singleton(op.AppStore.ext.AppStore, 'AppStore')
    # Colors.i = config.register_singleton(op.Colors.ext.Colors, 'Colors')
```

Once this runs, any script — externalized or temporary — can import and use global extensions with full autocomplete and correct runtime values:

```python
from AppStore import AppStore
from App import App

curState = AppStore.i.GetString(App.i.APP_STATE)
print(f"Current App State: {curState}")
```

This pattern gives the same convenience as `op.AppStore` / `op.App` at runtime, plus Pylance autocomplete on every method and attribute — in both externalized `.py` scripts and non-externalized temp DATs.

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

__import__('penner').easeInOutExpoNorm(op('filter1')[0])
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
  subdirs = ['python', 'python/util', 'python/app', 'python/net']
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