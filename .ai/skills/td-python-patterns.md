---
name: td-python-patterns
description: Task-oriented TouchDesigner Python patterns. Use this when working with operators, parameters, DATs, CHOPs, TOPs, storage, or timing.
---

# TouchDesigner Python Patterns

Code patterns organized by task. All examples assume standard TD Python context (globals `td`, `op`, `me`, `parent`, `ui`, `absTime` are available).

## Creating and Connecting Operators

```python
# Create an operator inside a COMP
comp = op('/project1/base1')
noise = comp.create(noiseTOP)          # Create by class
text = comp.create(textDAT, 'myText')  # Create with name

# Connect operators (wire outputs to inputs)
noise.outputConnectors[0].connect(comp.create(levelTOP))

# Disconnect
noise.outputConnectors[0].disconnect()

# Find children
comp.findChildren(type=TOP)                   # All TOPs in comp
comp.findChildren(type=DAT, name='config*')   # DATs matching pattern
comp.findChildren(depth=1)                    # Direct children only
```

## DAT Table Operations

```python
table = op('table1')

# Cell access — always tuple indexing, always .val
table[0, 0].val              # By row/col index
table['rowName', 'colName'].val  # By header names
table[0, 'colName'].val     # Mixed

# Row/col counts
table.numRows
table.numCols

# Append data
table.appendRow(['a', 'b', 'c'])
table.appendCol(['x', 'y', 'z'])
table.insertRow(['new'], 2)     # Insert at row index 2

# Delete
table.deleteRow(0)
table.deleteCol('colName')
table.clear()                   # Remove all rows (keeps headers with clear(keepFirstRow=True))

# Bulk text access
table.text                      # Entire table as tab-delimited string
table.csv                       # Entire table as CSV string (read only convenience)

# JSON (for DATs holding JSON text)
dat = op('text1')
obj = dat.jsonObject            # Parse text content as JSON dict/list

# Iterate rows
for row in range(table.numRows):
    for col in range(table.numCols):
        print(table[row, col].val)
```

## CHOP Channel Operations

```python
chop = op('constant1')

# Access a channel by name
chan = chop['chan1']
val = chan.eval()               # Current value (most common)

# Channel info
chop.numChans                   # Number of channels
chop.numSamples                 # Number of samples
chan.name                       # Channel name

# Iterate channels
for i in range(chop.numChans):
    chan = chop.chan(i)          # By index
    print(chan.name, chan.eval())

# Sample access (multi-sample CHOPs)
chan[0]                         # First sample value
chan[-1]                        # Last sample value
chan.numpyArray()               # All samples as numpy array

# Common pattern: read a CHOP value in an expression
# In a parameter expression field:
op('constant1')['chan1']        # Returns the evaluated value directly

# transform or remap a number:
# in a constant, referencing another operator's channel with some math:
__import__('penner').easeInOutExpoNorm(op('filter1')[0])
# or in a script CHOP:
def onCook(scriptOp: scriptCHOP):
	scriptOp.clear()
	chan = scriptOp.appendChan('chan1')
	inputVal = scriptOp.inputs[0][0][0]
	chan[0] = __import__('penner').easeInOutExpoNorm(inputVal)
```

## TOP Pixel Access

```python
top = op('noise1')

# Dimensions (operator properties, NOT parameters)
top.width
top.height

# Sample a pixel (returns a tuple of floats, one per channel)
r, g, b, a = top.sample(x=100, y=50)

# Numpy array (requires numpy)
arr = top.numpyArray()          # Shape: (height, width, 4) — RGBA float32
# Note: row 0 is the bottom of the image

# Save to file
top.save('output.png')
top.save('output.exr')

# Copy TOP data to another TOP
top.copyNumpyArray(arr)         # Write numpy array into a scriptTOP
```

## SOP Geometry Access

```python
sop = op('box1')

# Points
sop.numPoints
sop.points                      # Collection of Point objects
point = sop.points[0]
point.x, point.y, point.z      # Position components
point.P                         # Position as AttributeData

# Primitives
sop.numPrims
sop.prims
prim = sop.prims[0]
prim.center                     # Center position (tdu.Position)
prim.normal                     # Normal vector (tdu.Vector)

# Attributes
sop.pointAttribs                # Point attribute collection
sop.primAttribs                 # Primitive attribute collection
sop.vertexAttribs               # Vertex attribute collection

# Evaluate surface position
pos = prim.eval(u=0.5, v=0.5)  # Parametric surface evaluation

# Script SOP pattern
def onCook(scriptOp):
    scriptOp.clear()
    # Add points
    p = scriptOp.appendPoint()
    p.x, p.y, p.z = 0, 1, 0
    # Add polygon
    poly = scriptOp.appendPoly(3, closed=True)  # Triangle
```

## COMP Operations

```python
comp = op('base1')

# Create child operators
comp.create(noiseTOP, 'myNoise')

# Find children
comp.findChildren(type=TOP, depth=1)
comp.findChildren(name='noise*')

# Internal operator (the component's own network)
comp.currentChild               # Currently displayed child

# Clone/copy
comp.copy(op('base2'))          # Copy operator into this comp

# Parent shortcuts
parent()                        # Immediate parent COMP
parent.MyShortcut               # Named parent shortcut
parent(2)                       # Grandparent
parent(3)                       # Great-grandparent
```

## Extensions

```python
# Extension class (lives in a Text DAT inside the COMP)
class MyExtension:
    def __init__(self, ownerComp):
        self.ownerComp = ownerComp
        # Initialize state here

    def MyMethod(self):
        # Access the owning component
        self.ownerComp.op('noise1').par.roughness = 0.5

    def PromoteMethod(self):
        """Methods can be promoted to make them callable from outside, and must start with an uppercase letter."""
        pass

# Accessing extensions
me.ext.MyExtension              # From within the COMP or children
op('base1').ext.MyExtension     # From anywhere
op('base1').extensions          # List of all extension objects

# Check readiness
op('base1').extensionsReady     # True when extensions are compiled

# Re-initialize
op('base1').initializeExtensions()
```

## Storage

Persistent key-value storage on any operator. Survives cook cycles, optionally survives file save/load.

```python
# Store
op('base1').store('counter', 0)
op('base1').store('config', {'host': '127.0.0.1', 'port': 8080})

# Fetch
count = op('base1').fetch('counter', 0)        # With default
config = op('base1').fetch('config')

# Fetch with hierarchy search
val = op('child').fetch('key', search=True)     # Searches parent COMPs

# Store default on fetch miss
val = op('base1').fetch('key', 42, storeDefault=True)

# Remove
op('base1').unstore('counter')
op('base1').unstore('temp*')    # Pattern matching

# Startup values (for non-serializable objects like sockets)
op('base1').store('conn', mySocket)
op('base1').storeStartupValue('conn', None)     # Will be None on file load
```

## Delayed Execution

```python
# Run code after a delay
run("op('text1').text = 'done'", delayFrames=60)

# Run a DAT script
run(op('script1'), delayFrames=10)

# Run at end of current frame
run("print('end of frame')", endFrame=True)

# Run with specific context
run("print(me)", fromOP=op('base1'))

# Millisecond delay
run("print('later')", delayMilliSeconds=1000)

# Cancel pending runs
td.runs.clear()                 # Cancel all pending runs
```

## Time

```python
# Absolute time (never resets, always increases)
absTime.frame                   # Absolute frame count (int)
absTime.seconds                 # Absolute seconds (float)
absTime.step                    # Frames since last cook (usually 1)
absTime.stepSeconds             # Seconds since last cook

# Timeline time (resets with timeline, affected by play/pause)
me.time.frame                   # Current frame on this timeline
me.time.seconds                 # Current seconds on this timeline
me.time.rate                    # FPS
me.time.play                    # True if playing (read/write)
me.time.loop                    # True if looping (read/write)
me.time.start                   # Timeline start frame
me.time.end                     # Timeline end frame

# In parameter expressions
me.time.frame                   # Timeline-relative frame
me.time.seconds                 # Timeline-relative seconds

# Tempo
me.time.tempo                   # BPM
me.time.signature1              # Time signature numerator
me.time.signature2              # Time signature denominator
```

## UI and Dialogs

```python
# Status bar message
ui.status = 'Processing...'

# Message dialog
ui.messageBox('Title', 'Message text')

# Open file dialog
path = ui.chooseFile(load=True, fileTypes=['toe', 'tox'])

# Open folder dialog
folder = ui.chooseFolder()

# Clipboard
ui.clipboard = 'copied text'
text = ui.clipboard
```

## See Also

- [.ai/skills/td-skills.md](.ai/skills/td-skills.md) — Philosophy, retrieval strategy, class hierarchy
- [.ai/skills/td-common-mistakes.md](.ai/skills/td-common-mistakes.md) — Mistake/correction pairs
