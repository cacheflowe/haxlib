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

Bridges TD extension instances into `sys.modules` so DAT scripts can access them via the singleton pattern (see `VSCODE_PYTHON_SETUP.md`):

```python
App.i = config.register_singleton(self, 'App')
AppStore.i = config.register_singleton(op.AppStore.ext.AppStore, 'AppStore')
```

#### Bootstrap() — the configuration loading sequence

This is where all configuration sources are merged into AppStore:

```python
def Bootstrap(self):
    self.AppStore.LoadFile()                              # 1. persisted values
    config.LoadEnvFile(os.path.join(project.folder, '.env'))  # 2. .env file
    self.AppStore.par.Applydefaults.pulse()               # 3. defaults table
    td.reloadModules = config.ReloadModules
```

---

## Configuration Sources & Load Order

All configuration ends up in AppStore. There are two levels of persistence before `Bootstrap()` even runs:

- **`.toe` file** — TD saves DAT table contents in the project file. The `storeTable` already has values from the last project save when AppStore initializes.
- **TSV backup file** — a separate on-disk backup written by `AppStore.SaveFile()`, loaded explicitly in Bootstrap.

Sources then load in this order during `Bootstrap()`:

| Order | Source | Method | Notes |
|-------|--------|--------|-------|
| 0 | `.toe` project file | (automatic, TD) | storeTable contents from last project save |
| 1 | TSV backup file | `AppStore.LoadFile()` | Overwrites .toe table with last runtime state |
| 2 | `.env` file | `config.LoadEnvFile()` | Overwrites persisted values for matching keys |
| 3 | Defaults table | `AppStore.SetDefaults()` | Only sets keys not already present (`force=False`) |

**Result:** runtime state from TSV wins over stale .toe values; `.env` overrides both for environment-specific config; defaults fill in anything missing.

### Shell / OS environment variables

OS-level vars (set before TD launches via `run-td-app-plus-env-var.cmd` or system env) are pulled into AppStore via explicit calls to:

```python
config.LoadSystemEnvironmentVar('my_key', default_value)
```

This does store into AppStore (via `StoreValueInStore`) — it is not automatic during Bootstrap, but any call to it will push the value into AppStore with the same type inference as `.env` loading.

### .env type inference

`config.LoadEnvFile()` infers types when storing to AppStore:

```python
"true" / "false"  → SetBoolean()
"123"             → SetFloat()   (digits only)
everything else   → SetString()
```

Gotchas:
- `"yes"`, `"1"`, `"0"` are stored as **strings**, not booleans
- `"123abc"` is stored as a **string**, not a number
- `.env` loading **overwrites** persisted values — environment config takes precedence

---

## AppStore Internals

AppStore maintains three parallel representations of state:

1. **`self.dependencies`** — dict of `tdu.Dependency` objects. Granular reactivity: only operators listening to a specific key cook when that key changes.
2. **`self.storeTable`** — DAT table with columns `[key, value, valueType, sender, eventId]`. Any operator watching the whole table cooks on any change.
3. **`self.numericTable`** — CHOP mirror of numeric values only.

`SetValue()` updates all three in sequence, then calls `NotifyListeners()`.

---

## Known Issues & Silent Failures

### Values set multiple times in a single frame

During `Bootstrap()`, a key can be written up to three times in one frame:

1. `LoadFile()` → restores persisted value
2. `LoadEnvFile()` → overwrites with .env value (if key present)
3. `SetDefaults()` → skipped if key already exists (`force=False`)

Each `SetValue()` call updates the dependency, the table, generates a new `eventId`, and fires `NotifyListeners()`. If any listeners are registered by Bootstrap time (unlikely but possible), they will receive multiple callbacks for the same key in a single frame with no batching.

**Risk:** anything downstream that reacts to AppStore values during init may cook multiple times or receive intermediate values.

### tdu.Dependency equality check

`tdu.Dependency` may not fire a cook if the new value equals the existing value. The comment in `SetValue()` acknowledges this:

```python
# Force Modified logic if value is same?
# tdu.Dependency usually handles equality check, use .modified() if you need to force
```

If `.env` reloads the same value that was persisted, the dependency update may be a no-op — but `NotifyListeners()` is still called unconditionally. Listeners will be notified even when the value hasn't changed.

### LoadFile() silent failures

```python
def LoadFile(self):
    filePath = self.ownerComp.par.Backupfile.eval()
    if filePath:
        self.fileInTable.par.refreshpulse.pulse()
        self.storeTable.copy(self.fileInTable)
        self.SyncFromTable()
```

- If `Backupfile` parameter is empty → silently does nothing
- If the file doesn't exist → `filein_backup` loads nothing, `storeTable` may be cleared
- No error logging if the file is missing or malformed

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

### Listener logic bug in AddListener()

```python
elif hasattr(listener, f'On_{key}'):
    # adds to key listeners
else:
    print(f"[AppStore] Listener already exists: {listener}")
```

The `else` branch fires when the listener does **not** have the required `On_{key}` method — but the print message says "already exists", which is misleading. The listener is silently not registered with no useful error.

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

## Recommendations

- **Add logging to LoadFile()** — at minimum print a warning if the backup file is missing
- **Batch AppStore writes during init** — consider a flag that suppresses `NotifyListeners()` during Bootstrap and fires one notification pass after all sources are loaded
- **Fix the AddListener() else branch** — log the real reason (missing method) not "already exists"
- **Validate curState** before the `run()` string in `SetInitialMode()`
- **Consider a `force=True` variant of LoadEnvFile()** with explicit logging when .env overwrites a persisted value — currently silent
