# TouchDesigner Extension Template

Complete template for creating Python extensions attached to COMPs, with proper initialization, storage, lifecycle callbacks, and cleanup.

## Documentation

- [Extensions](https://derivative.ca/UserGuide/Extensions)
- [Experimental Extensions](https://derivative.ca/UserGuide/Experimental:Extensions)
- [TDStoreTools](https://derivative.ca/UserGuide/TDStoreTools)
- [TDFunctions](https://docs.derivative.ca/TDFunctions)
- [Dependency Class](https://derivative.ca/UserGuide/Dependency_Class)
- [CallbacksExt Extension](https://derivative.ca/UserGuide/CallbacksExt_Extension)

## Full Template

```python
from TDStoreTools import StorageManager
import TDFunctions as TDF
import tdu

class NewExtension:
	"""
	NewExtension description
	"""

	def __init__(self, ownerComp: baseCOMP):
		self.ownerComp: baseCOMP = ownerComp

		# Dependable properties — reset when extension is re-initialized
		TDF.createProperty(self, 'MyProp1', value=3, dependable=True, readOnly=False)
		self.MyProp2 = tdu.Dependency(3)

		# Update dependable props:
		# self.MyProp1 = 11
		# self.MyProp2.val = 5

		# StorageManager — persists between saves (survives file reload)
		self.stored = StorageManager(self, ownerComp, [
			{'name': 'ExampleProp', 'default': 13, 'readOnly': False,
			 'property': True, 'dependable': True},
		])
		self.ExampleProp = 14

	def onInitTD(self):
		"""Called after the extension is fully initialized and attached."""
		debug("onInitTD called")

	def Reset(self):
		"""Reset extension state."""
		return

	###################################################
	# Cleanup — handles both old and new TD versions
	###################################################

	def __delTD__(self):
		"""Pre-experimental cleanup (older TD versions)."""
		self.dispose()

	def onDestroyTD(self):
		"""Experimental cleanup (newer TD versions)."""
		self.dispose()

	def __del__(self):
		"""Called after onDestroyTD."""
		return

	def dispose(self):
		"""Centralized cleanup logic."""
		debug('[NewExtension] Cleaning up')
		# self.stored.clear()  # Uncomment to reset stored values
```

## Key Concepts

### Dependable Properties

Properties that trigger downstream updates when changed (like TD's dependency system):

```python
# Method 1: TDF.createProperty — creates a Python property with dependency tracking
TDF.createProperty(self, 'Scale', value=1.0, dependable=True, readOnly=False)
# Read: self.Scale -> 1.0
# Write: self.Scale = 2.0 (triggers dependents)

# Method 2: tdu.Dependency — lower-level, explicit .val access
self.MyDep = tdu.Dependency(5)
# Read: self.MyDep.val -> 5
# Write: self.MyDep.val = 10 (triggers dependents)
```

For complex objects (dicts, lists), use Deeply Dependable Collections from [TDStoreTools](https://derivative.ca/UserGuide/TDStoreTools#Deeply_Dependable_Collections).

### StorageManager

Persists values between saves. Because `__init__()` runs every time the extension reinitializes, normal instance variables reset on save. StorageManager solves this:

```python
self.stored = StorageManager(self, ownerComp, [
	{'name': 'Counter', 'default': 0, 'readOnly': False,
	 'property': True, 'dependable': True},
	{'name': 'Config', 'default': {}, 'readOnly': False,
	 'property': True, 'dependable': False},
])
```

Each entry creates a property on `self` backed by operator storage. `dependable: True` means changes trigger downstream cook.

### Lifecycle Methods

| Method | When Called |
|--------|-----------|
| `__init__(ownerComp)` | Extension created or re-initialized (every save) |
| `onInitTD()` | After extension is fully attached to component |
| `__delTD__()` | Pre-experimental cleanup on destroy/reinit |
| `onDestroyTD()` | Experimental cleanup on destroy/reinit |
| `__del__()` | Python garbage collection (after onDestroyTD) |

### Accessing Extensions

```python
# From within the COMP or its children
me.ext.NewExtension

# From anywhere
op('base1').ext.NewExtension
op('base1').ext.NewExtension.MyMethod()

# Check if ready
op('base1').extensionsReady  # True when compiled

# Re-initialize
op('base1').initializeExtensions()
```

### Externalizing Extension Files

Store `.py` files alongside `.tox` for version control:

```python
# Relative external file path to tox
parent().par.externaltox.eval().replace('.tox', '.py')
```

Set the "External" parameter on the extension's Text DAT to point to the `.py` file. Changes in VS Code auto-reload in TD.

## See Also

- [td-oop.md](td-oop.md) — OOP architecture concepts in TD
- [td-python-style.md](td-python-style.md) — Python coding conventions
- [td-python-patterns.md](td-python-patterns.md) — Code patterns (storage, extensions)
