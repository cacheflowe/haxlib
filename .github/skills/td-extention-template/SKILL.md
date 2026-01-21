# TouchDesigner Extension Template

A complete template for creating TouchDesigner extensions with proper initialization, storage management, lifecycle callbacks, and cleanup methods.

## Overview

Extensions in TouchDesigner allow you to attach Python classes to components, providing object-oriented programming capabilities. This template includes:
- Proper initialization with dependable properties
- Persistent storage using StorageManager
- Lifecycle callbacks (onInitTD, cleanup methods)
- AppStore visibility callbacks
- Cleanup/disposal patterns for different TD versions

## Template Code

```python
from TDStoreTools import StorageManager
import TDFunctions as TDF
import tdu

class NewExtension:
	"""
	NewExtension description
	"""

	def __init__(self, ownerComp:baseCOMP):
		self.ownerComp:baseCOMP = ownerComp
		# Create dependable properties that reset when extension is saved
		TDF.createProperty(self, 'MyProp1', value=3, dependable=True, readOnly=False) 
		self.MyProp2 = tdu.Dependency(3)

		# Example update different dependable props:
		# self.MyProp1 = 11
		# self.MyProp2.val = 5

		# Create dependables with StorageManager, which persist between saves
		self.stored = StorageManager(self, ownerComp, [
			{'name': 'ExampleProp', 'default': 13, 'readOnly': False, 'property': True, 'dependable': True},
		])
		self.ExampleProp = 14
	
	def onInitTD(self):
		# Called after the extension is fully initialized and attached to the component
		debug("onInitTD called") 

	def Reset(self):
		return

	# AppStoreToggle callbacks

	def On_show(self):
		self.Reset()  

	def On_hidden(self):
		self.Reset()

	# Extension cleanup methods (new and old versions of TD)

	def __delTD__(self):
		self.dispose()

	def onDestroyTD(self):
		self.dispose()

	def __del__(self):
		# called after onDestroyTD
		return
		
	def dispose(self):
		debug('[NewExtension] Cleaning up')
		# self.stored.clear() # Uncomment to reset stored values

```

## Key Concepts

### Dependable Properties

- **TDF.createProperty()**: Creates properties that reset when extension is saved
- **tdu.Dependency()**: Alternative method for creating dependable properties
- **StorageManager**: Creates properties that persist between saves

### Lifecycle Methods

- **`__init__()`**: Called when extension is first created
- **`onInitTD()`**: Called after extension is fully initialized and attached
- **`__delTD__()` / `onDestroyTD()`**: Called when extension is being destroyed
- **`dispose()`**: Custom cleanup method to centralize cleanup logic

### AppStore Callbacks

- **`On_show()`**: Called when component becomes visible in AppStore
- **`On_hidden()`**: Called when component is hidden in AppStore