---
name: td-appstore
description: AppStore state management for haxlib — typed API, reactivity system, WebSocket sync, persistence, and Bootstrap load order. Use when reading/writing app state, setting up listeners, or debugging sync behavior.
---

# AppStore

AppStore is the centralized state management extension for haxlib TouchDesigner projects. It provides a reactive key-value store with type-aware getters/setters, end-of-frame batched notifications, WebSocket synchronization, and file persistence.

---

## Quick Reference

```python
# Read values (from any script or extension)
from AppStore import AppStore

AppStore.i.GetFloat('app_w')              # → 1920.0
AppStore.i.GetString('app_state')         # → 'gameplay'
AppStore.i.GetBoolean('is_production')    # → False
AppStore.i.HasValue('some_key')           # → True/False

# Write values
AppStore.i.SetFloat('app_w', 1920)
AppStore.i.SetString('app_state', 'attract')
AppStore.i.SetBoolean('is_production', True)

# Write + broadcast over WebSocket
AppStore.i.SetFloat('score', 100, broadcast=True)

# Listen for changes
AppStore.i.AddListener(self)              # all keys → OnAppStoreValueChanged(key, value, type)
AppStore.i.AddListener(self, 'app_state') # one key  → On_app_state(key, value, type)
```

---

## Architecture

### Three-Layer Storage

AppStore maintains three parallel representations of state, each serving a different consumer:

| Layer | Type | Purpose |
|-------|------|---------|
| `self.dependencies` | `Dict[str, tdu.Dependency]` | Granular reactivity — only operators reading a specific key cook when it changes |
| `self.storeTable` | `tableDAT` | Persistent table (`table_store_dictionary`) — any operator watching the whole table cooks on any change |
| `self.numericTable` | `dattoCHOP` | CHOP mirror of numeric values — for operators that need channel data |

`SetValue()` updates all three in sequence. The table has columns: `[key, value, valueType, sender, eventId]`.

### Singleton Access

AppStore uses the singleton pattern for typed access from any script:

```python
from AppStore import AppStore

# After App.RegisterSingletons() has run:
AppStore.i.GetFloat('app_w')   # fully typed, autocomplete works
```

Inside `App.py`, use the `@property` pattern instead (see `docs/VSCODE_PYTHON_SETUP.md` for why):

```python
self.AppStore.GetFloat('app_w')  # resolves via op.AppStore at runtime
```

---

## Reactivity System

### tdu.Dependency (immediate, TD-level)

When `SetValue()` updates `self.dependencies[key].val`, any TD operator that previously read that dependency will cook immediately within the same frame. This is TD's native reactivity — it cannot be deferred.

Use case: a parameter expression like `op.AppStore.GetFloat('app_w')` in a node will automatically re-cook when `app_w` changes, with no listener registration needed.

### Python Listeners (batched, end-of-frame)

Python callback listeners are notified at the **end of each frame**, not immediately on `SetValue()`. This provides:

- **Deduplication** — if a key is set 3 times in one frame, listeners fire once with the final value
- **Consistency** — all values are settled before any listener reacts
- **Stability** — off-thread writes (WebSocket messages) are coalesced

#### How it works

1. `SetValue()` detects a change and adds the key to `_pendingKeys`
2. At frame end, an Execute DAT calls `FlushNotifications()`
3. `FlushNotifications()` reads the current value from the dependency cache and fires listeners

```
SetValue('x', 1)  ─┐
SetValue('x', 2)  ─┤  within same frame
SetValue('x', 3)  ─┘
                        ... frame end ...
FlushNotifications() → listeners receive ('x', 3, 'number') once
```

#### Execute DAT setup

Inside the AppStore COMP, create a DAT Execute node named `execute_frame_end`:
- Parameter **End** = On (all others off)
- Script:

```python
def onFrameEnd(frame):
	me.parent().ext.AppStore.FlushNotifications()
```

### Registering Listeners

**All-key listener** — receives every value change:

```python
class MyExtension:
    def __init__(self, ownerComp):
        AppStore.i.AddListener(self)

    def OnAppStoreValueChanged(self, key, value, type):
        print(f"{key} changed to {value}")
```

**Single-key listener** — receives only changes for a specific key:

```python
class MyExtension:
    def __init__(self, ownerComp):
        AppStore.i.AddListener(self, 'app_state')

    def On_app_state(self, key, value, type):
        print(f"State is now: {value}")
```

The method name must be `On_{key}` — if it's missing, AddListener prints an error and does not register.

#### Listener cleanup

Defunct listeners (stale references from extension reloads) are cleaned up:
- Automatically when `AddListener()` is called (keeps newest instance per ownerComp)
- Automatically when `NotifyListeners()` encounters an exception on a listener call

---

## Value Types

All values are stored as strings in the table but accessed through typed getters/setters:

| Type | Constant | Setter | Getter | Storage |
|------|----------|--------|--------|---------|
| Number | `TYPE_NUMBER` | `SetFloat(key, 1.5)` | `GetFloat(key, default=0.0)` | `"1.5"` |
| String | `TYPE_STRING` | `SetString(key, 'hello')` | `GetString(key, default='')` | `"hello"` |
| Boolean | `TYPE_BOOLEAN` | `SetBoolean(key, True)` | `GetBoolean(key, default=False)` | `"True"` |

`GetBoolean` accepts `"true"`, `"1"`, or `"1.0"` (case-insensitive) as True — matches TD's convention that 0/1 is interchangeable with False/True. Anything else is False.

`GetFloat` returns the default if the stored value can't be parsed as a float.

---

## Persistence

### File Backup (TSV)

AppStore can save/load its table to a TSV file on disk:

- **SaveFile()** — writes `storeTable` to the path in the `Backupfile` parameter. Skipped during the first 5 seconds after launch to avoid saving incomplete init state.
- **LoadFile()** — reads the TSV and merges each row into the store via `SetValue()`. Keys not in the file are preserved (row-by-row merge, not table replace).

### .toe File

TD automatically persists DAT table contents in the `.toe` project file. When the project opens, `storeTable` already contains whatever was present at last save. This is the lowest-priority data source — everything else overwrites it during Bootstrap.

### Defaults Table

A `in_default_values` DAT inside the AppStore COMP defines baseline key/value/type rows. `SetDefaults(force=True)` writes all of them into the store unconditionally.

---

## Bootstrap Load Order

During `App.Bootstrap()`, configuration sources are loaded in precedence order (later wins):

| Order | Source | Method | Behavior |
|-------|--------|--------|----------|
| 0 | `.toe` file | (automatic) | Already in storeTable when AppStore initializes |
| 1 | Defaults table | `SetDefaults(force=True)` | Overwrites .toe values — establishes baseline |
| 2 | Persisted TSV | `LoadFile()` | Merges persisted runtime state (row-by-row) |
| 3 | `.env` file | `config.LoadEnvFile()` | Overwrites for environment-specific config |

Notifications are fully suppressed during Bootstrap (`_suppressNotify = True`). No listeners fire until after all layers are loaded and Bootstrap completes.

Hard-coded values set after Bootstrap (e.g. `App.AddOpPaths()`) have the highest precedence.

---

## WebSocket Synchronization

AppStore is designed as part of a multi-app system on a local network, where a central WebSocket server is the authoritative source for shared state. TD apps broadcast their intent to change a value; the server validates and echoes the change back to all connected clients (including the originating one). This **server-as-truth** pattern ensures all clients converge on the same state.

### Local vs. shared state — when to use `broadcast`

Every value in AppStore is one of two things:

- **Local state** (`broadcast=False`, the default) — internal to this TD app. Used for communication between components inside a single project: UI toggles, render flags, intermediate computed values, anything that doesn't need to leave this process. Listeners react via the standard end-of-frame batched notifications.

- **Shared state** (`broadcast=True`) — part of the distributed system. The value is owned by the WebSocket server and synchronized across all connected clients (other TD apps, browser UIs, control surfaces, etc.). Useful even within a single-app deployment: it lets a browser-based control panel drive TD state without bespoke integration code, and scales naturally if you later add a second app to the network.

The same key/value/listener machinery is used for both — the only difference is whether the write goes through the server first.

### The `broadcast=True` flag

Pass `broadcast=True` to any setter to participate in distributed state:

```python
AppStore.i.SetFloat('score', 100, broadcast=True)
```

Behavior depends on connection state:

| Connection | Behavior |
|------------|----------|
| Connected | Sends over the wire, **does NOT update local state**. Waits for the server echo via `MessageReceived` to update locally. |
| Disconnected | Falls back to a local-only update so the app keeps working offline. The key + write count is tracked silently. |

This connectivity check is centralized inside `SetValue()` — callers don't need to call `IsConnected()` themselves.

A single multiline banner is printed on each connection toggle (disconnect, then reconnect). The reconnect banner includes a summary of broadcast writes that fell back to local during the outage — so a flood of fallback writes produces one log block, not one line per write.

### Wire format

Sent over the WebSocket:

```json
{"store": true, "key": "score", "value": 100, "type": "number", "sender": "td-001"}
```

The `sender` field identifies the originating client and prevents echo loops in multi-client scenarios.

### Receiving (server → TD)

Incoming messages with `{"store": true}` are parsed by `MessageReceived()` and applied locally via `SetValue(..., broadcast=False)`. This is how echoed broadcasts make it back into the local store.

### Reconnect behavior

On reconnect, the server is expected to send a snapshot of full server state as JSON. The parser for this snapshot is not yet implemented — when it arrives, all shared keys will sync to the authoritative server values.

In the meantime, no automatic re-sync happens on reconnect — both sides resume from their last known states and converge through subsequent writes.

### Connection state API

- `IsConnected()` — check if WebSocket is active
- `StartWebServer()` — launch the web server script in a background thread
- `CheckSocketReconnect()` — pulse the WebSocket reset if disconnected

The COMP color indicates connection state: yellow = disconnected, green = connected.

---

## API Reference

### Getters

| Method | Returns | Notes |
|--------|---------|-------|
| `HasValue(key)` | `bool` | Checks dependency cache |
| `GetFloat(key, default=0.0)` | `float` | Returns default on missing key or parse error |
| `GetString(key, default='')` | `str` | Reading triggers tdu.Dependency reactivity |
| `GetBoolean(key, default=False)` | `bool` | True for `"true"`, `"1"`, `"1.0"` (case-insensitive) |
| `GetStoreDat()` | `DAT` | Direct access to storeTable |
| `GetStoreChop()` | `CHOP` | Direct access to numeric CHOP |

### Setters

| Method | Notes |
|--------|-------|
| `SetValue(key, value, valueType, sender, broadcast)` | Low-level, all others call this |
| `SetFloat(key, value, broadcast=False)` | Stores as TYPE_NUMBER |
| `SetString(key, value, broadcast=False)` | Stores as TYPE_STRING |
| `SetBoolean(key, value, broadcast=False)` | Stores as TYPE_BOOLEAN |
| `SetFromString(key, rawValue, broadcast=False)` | Type-inferred setter for string-only sources (.env, env vars). Bool/float/leading-zero/string rules. |

### Listeners

| Method | Notes |
|--------|-------|
| `AddListener(listener, key=None)` | None = all keys, else requires `On_{key}` method |
| `RemoveListener(listener)` | Removes from all subscriptions |

### Utility

| Method | Notes |
|--------|-------|
| `ClearData()` | Wipes store and re-applies defaults |
| `RemoveValue(key, broadcast=False)` | Removes from both cache and table |
| `SaveFile()` | Writes table to Backupfile path (skips first 5s) |
| `LoadFile()` | Merges TSV backup into store |
| `SetDefaults(force=False)` | Applies defaults table; force=True overwrites existing |
| `PrintValues()` | Debug dump to textport |
| `FlushNotifications()` | Called by Execute DAT at frame end — do not call manually |

---

## Internal Nodes

These operators live inside the AppStore COMP:

| Node | Type | Purpose |
|------|------|---------|
| `table_store_dictionary` | tableDAT | Primary key-value table |
| `datto_store_numbers` | dattoCHOP | CHOP mirror of numeric values |
| `filein_backup` | tableDAT | Reads the TSV backup file |
| `in_default_values` | tableDAT | Default key/value/type definitions |
| `websocket1` | websocketDAT | WebSocket client for browser sync |
| `constant_active` | constantCHOP | Connection state flag (0/1) |
| `constant_active_color` | constantTOP | COMP color indicator |
| `execute_frame_end` | executeDAT | Calls FlushNotifications() at frame end |

## See Also

- [.ai/skills/td-startup.md](.ai/skills/td-startup.md) — full App bootstrap sequence and config load order
- [.ai/skills/td-oop.md](.ai/skills/td-oop.md) — extension patterns and global op references
