---
name: td-startup
description: haxlib App startup sequence — extension init order, Bootstrap config load priorities (.toe → defaults → TSV → .env → OS vars), known issues and silent failures. Use when debugging init order or implementing startup behavior.
---

# App Startup Sequence

This document describes how the `haxlib` TouchDesigner project initializes, how configuration values flow into AppStore, and known issues to watch for.

---

## Architecture Overview

The project uses a single top-level `App` extension attached to the `/project1` COMP. `App` is the entry point — the first user code that runs — and is responsible for bootstrapping all global state.

Global extensions (`AppStore`, `Colors`, etc.) live as **child COMPs** of `/project1`. TD initializes children before parents, so by the time `App.__init__` runs, all child extensions are already live and accessible.

```
/project1  ← App extension (entry point, runs last)
  /AppStore  ← AppStore extension (runs first)
  /Colors    ← Colors extension (runs first)
  ...
```

---

## Startup Flow

### Phase 0 — Shell / OS (optional)

If launched via `scripts/start-all.cmd`:

```
start-all.cmd
  ├─ td-start.cmd        → opens haxlib.toe
  └─ web-server-start.cmd → starts Vite + WebSocket server in parallel
```

`run-td-app-plus-env-var.cmd` is an alternative launcher that sets OS-level environment variables before opening TD. These variables are later read by `config.LoadSystemEnvironmentVar()`.

---

### Phase 1 — TD Loads, Child Extensions Initialize

`AppStore.__init__` runs before `App`:

1. `initListeners()` — empty listener registry
2. `initStore()` — bind to internal DAT/CHOP operators (`table_store_dictionary`, `filein_backup`, `in_default_values`)
3. `initDependencies()` → `SyncFromTable()` — create `tdu.Dependency` objects from any existing table data
4. `initWebSocket()` — set disconnected state, attempt reconnect

At this point `AppStore` is live and its `storeTable` DAT already contains whatever values were present when the `.toe` file was last saved — TD persists DAT table contents in the project file itself. `SyncFromTable()` reads those into the dependency cache. However, the file backup (the TSV on disk) and defaults have not been applied yet.

---

### Phase 2 — App.__init__ Runs

```python
def __init__(self, ownerComp):
    self.ownerComp = ownerComp
    self.RegisterSingletons()  # ← first
    self.Bootstrap()
    self.AddOpPaths()
    self.ResizeExtensionNodes()
    self.AddStoreListeners()
    # deferred:
    # SetInitialMode()     → frame +5
    # LaunchOutputWindow() → frame +1000 (production only)
```

#### RegisterSingletons()

Bridges TD extension instances into `sys.modules` so DAT scripts can access them via the singleton pattern (see `docs/VSCODE_PYTHON_SETUP.md`):

```python
App.i = config.register_singleton(self, 'App')
AppStore.i = config.register_singleton(op.AppStore.ext.AppStore, 'AppStore')
```

#### Bootstrap() — the configuration loading sequence

This is where all configuration sources are merged into AppStore. Later sources overwrite earlier ones for matching keys:

```python
def Bootstrap(self):
    # Load order: defaults (lowest) → persisted file → .env → shell env → hard-coded (highest)
    self.AppStore.SetDefaults(force=True)
    self.AppStore.LoadFile()
    config.LoadEnvFile(os.path.join(project.folder, '.env'))
    self.LoadSystemEnvVars()
    td.reloadModules = config.ReloadModules

def LoadSystemEnvVars(self):
    # Project-specific OS env var imports (set by the launching script, with defaults)
    config.LoadSystemEnvironmentVar('sys_env_var', 'Default Value')
```

---

## Configuration Sources & Load Order

All configuration ends up in AppStore. There are two levels of persistence before `Bootstrap()` even runs:

- **`.toe` file** — TD saves DAT table contents in the project file. The `storeTable` already has values from the last project save when AppStore initializes.
- **TSV backup file** — a separate on-disk backup written by `AppStore.SaveFile()`, loaded explicitly in Bootstrap.

Sources load in this order during `Bootstrap()` — each layer overwrites the previous for matching keys:

| Order | Source | Method | Notes |
|-------|--------|--------|-------|
| 0 | `.toe` project file | (automatic, TD) | storeTable contents from last project save |
| 1 | Defaults table | `AppStore.SetDefaults(force=True)` | Overwrites .toe values — establishes baseline |
| 2 | TSV backup file | `AppStore.LoadFile()` | Merges persisted runtime state (row-by-row) |
| 3 | `.env` file | `config.LoadEnvFile()` | Overwrites for environment-specific config |
| 4 | OS env vars | `App.LoadSystemEnvVars()` → `config.LoadSystemEnvironmentVar()` | Project-specific keys set by the launching script — highest precedence among data sources |

**Result:** defaults establish baseline over stale .toe values; persisted file restores last runtime state; `.env` overrides for project config; OS env vars override for launch-time/installation-specific config. Hard-coded values set after Bootstrap (e.g. in `AddOpPaths()`) still have the absolute highest precedence.

### Shell / OS environment variables

OS-level vars (set before TD launches via `run-td-app-plus-env-var.cmd` or system env) are pulled into AppStore by `App.LoadSystemEnvVars()`, called at Bootstrap step 4. Each variable is loaded explicitly with a fallback default so the app is functional even when the launching script wasn't used:

```python
config.LoadSystemEnvironmentVar('my_key', default_value)
```

Add project-specific keys to `App.LoadSystemEnvVars()` — they're routed through `AppStore.SetFromString()` for the same type inference as `.env` loading.

### .env type inference

`config.LoadEnvFile()` and `config.LoadSystemEnvironmentVar()` route raw string values through `AppStore.SetFromString()`, which infers a type:

```
"true" / "false"      → SetBoolean()
parses as float()     → SetFloat()    (handles negatives, decimals, scientific notation)
leading-zero strings  → SetString()   ("0123" stays a string; "0" and "0.5" are numeric)
everything else       → SetString()
```

Gotchas:
- `"yes"`, `"on"`, `"1"`, `"0"` are stored as strings or numbers, **not booleans**. Use `GetBoolean()` to coerce — it accepts `"true"`, `"1"`, and `"1.0"` as True.
- `.env` loading **overwrites** persisted values — environment config takes precedence (logged via `(overwriting existing key: ...)`)

---

## Known Issues & Silent Failures

### Values set multiple times in a single frame

During `Bootstrap()`, a key can be written up to four times in one frame:

1. `SetDefaults(force=True)` → sets baseline value
2. `LoadFile()` → overwrites with persisted value (if key present in backup)
3. `LoadEnvFile()` → overwrites with .env value (if key present)
4. `LoadSystemEnvVars()` → overwrites with OS env value (if key wired in and present)

Each `SetValue()` call updates the dependency and the table, but `NotifyListeners()` is only called when the value actually changes (string equality check). This means redundant writes (e.g. .env sets the same value as the persisted file) do not trigger extra listener callbacks.

**Remaining risk:** if listeners are registered before Bootstrap completes (unlikely but possible), they may receive multiple callbacks for the same key within a single frame — once per layer that changes the value.

### tdu.Dependency equality check

`tdu.Dependency` may not fire a cook if the new value equals the existing value. `SetValue()` now performs its own string equality check before calling `NotifyListeners()`:

```python
changed = isNew or str(oldValue) != str(value)
if changed:
    self.NotifyListeners(key, value, valueType)
```

This means listeners are only notified when the value actually changes, regardless of how `tdu.Dependency` handles the cook internally.

### LoadFile() merge behavior

```python
def LoadFile(self):
    filePath = self.ownerComp.par.Backupfile.eval()
    if not filePath:
        print('[AppStore] LoadFile: no Backupfile path configured, skipping')
        return
    if not os.path.exists(filePath):
        print(f'[AppStore] LoadFile: file not found at {filePath}, skipping')
        return
    self.fileInTable.par.refreshpulse.pulse()
    for row in self.fileInTable.rows():
        ...
        self.SetValue(key, value, valueType, sender, False)
```

- Logs explicitly when path is missing or file not found (previously silent)
- Uses row-by-row merge via `SetValue()` instead of `storeTable.copy()` — preserves values from earlier layers (defaults) for keys not present in the backup file
- Each merged value goes through the same equality check as any other `SetValue()` call

### SaveFile() early-startup guard

```python
def SaveFile(self):
    if absTime.seconds < 5:
        print('[AppStore] SaveFile skipped - app just started')
        return
```

Saves are silently skipped for the first 5 seconds. If something triggers a save during init, it will be quietly ignored.

### Dependency cache vs table can diverge

`self.dependencies` is only synced from the table during `initDependencies()` and `LoadFile()`. If the `storeTable` DAT is modified directly (e.g. by a TD node, not via `SetValue()`), the dependency cache becomes stale. `GetFloat` / `GetString` / `GetBoolean` all read from `self.dependencies`, not the table.

### Listener logic in AddListener()

```python
elif hasattr(listener, f'On_{key}'):
    # adds to key listeners
else:
    print(f"[AppStore] Listener missing required 'On_{key}' method: {listener}")
```

The `else` branch fires when the listener does **not** have the required `On_{key}` method. The listener is not registered and an informative message is printed.

### cleanupDefunctListeners() only runs on AddListener()

Stale listener instances (from extension reloads) are only removed when a new listener is added. If listeners are never added after a reload, defunct references accumulate and will error when notified.

### SetInitialMode() state resumption

```python
if self.AppStore.GetString(App.APP_STATE, "NONE") != "NONE":
    run(f"op('{self.ownerComp.path}').SetState('{curState}')", delayFrames=5)
```

- During frames 0–5 the app is in an undefined state
- If `curState` contains a single quote or special characters, the `run()` string will break
- An empty string for `APP_STATE` (not "NONE") would try to set an empty state

---

## Recommendations (remaining)

- **Batch AppStore writes during init** — consider a flag that suppresses `NotifyListeners()` during Bootstrap and fires one notification pass after all sources are loaded
- **Validate curState** before the `run()` string in `SetInitialMode()`
- **Consider explicit logging when .env overwrites a persisted value** — currently silent
- **Add periodic cleanup of defunct listeners** — currently only runs on `AddListener()`

## See Also

- [.ai/skills/td-appstore.md](.ai/skills/td-appstore.md) — AppStore API reference (getters, setters, listeners, internal nodes)
- [.ai/skills/td-oop.md](.ai/skills/td-oop.md) — extension pattern and global op references
