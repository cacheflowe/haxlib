# OOP Architecture in TouchDesigner

How object-oriented programming concepts map to TouchDesigner's node-based world.

## Core Concept: COMP = Class

A **Base COMP** (or Container COMP) is the equivalent of a class in TD:

- **Parameters** are like properties — customize each instance
- **Extensions** (Python classes) add methods and lifecycle logic
- **Internal network** is the implementation
- **Out TOPs/CHOPs/etc.** are the outputs (interface)

```
COMP (Class)
├── Parameters (properties)
├── Extension .py (methods, lifecycle)
├── Internal nodes (implementation)
└── Out nodes (output interface)
```

## Instantiation Patterns

### Cloning

Clones are like instances of a class, scattered throughout a project. They stay synced with a **clone master**:

```python
# Clone master is typically at top level
replicant.par.clone = op('/project1/templates/MyTemplate')
```

Changes to the master propagate to all clones. Override individual parameters per-clone as needed.

### Replicators

A Replicator COMP is like a `for` loop that creates instances from a template. Driven by a data source (table DAT):

```python
# Each row in the table creates one replicant
# See td-replicator.md for callback patterns
```

### Manual Creation

```python
comp = op('/project1/container1')
new_op = comp.create(baseCOMP, 'myNewComp')
```

## Global Operator References

Global op shortcuts are like singletons — accessible from anywhere:

```python
# Set on /project1's COMP parameters:
# Global OP Shortcut: App
# Then access from anywhere:
op.App.SomeMethod()
op.AppStore.GetValue('key')
```

Best practice: keep global op references at the top level (`/project1`).

## Extensions as Methods

An extension class attached to a COMP provides methods and state:

```python
class MyFeature:
	def __init__(self, ownerComp: baseCOMP):
		self.ownerComp: baseCOMP = ownerComp

	def DoSomething(self):
		"""Public method — PascalCase"""
		self.ownerComp.op('noise1').par.roughness = 0.5

# Call from anywhere:
op('myFeature').ext.MyFeature.DoSomething()
# Or via global shortcut:
op.MyFeature.DoSomething()
```

## Python-Nodes-Python Flow

A common pattern: Python extension triggers nodes, nodes process data, an Execute DAT at the end calls back into the extension:

```
Extension method → sets parameters → nodes cook →
CHOP Execute DAT → calls extension method with results
```

Key rule: **no floating chopexec/datexec scripts** — keep logic in extensions, use Execute DATs only as callbacks into the extension.

## Externalizing for Version Control

Store `.tox` and `.py` files on disk for git tracking:

```python
# .py path relative to .tox
parent().par.externaltox.eval().replace('.tox', '.py')
```

- **COMP + .py extension = class** on disk
- Externalized Python enables normal AI-assisted dev workflows
- Changes in VS Code auto-reload in TD

## Querying Operators

`op()` and `ops()` are like `document.querySelector()` in JavaScript:

```python
op('noise1')                        # Single op by name
ops('noise*')                       # Multiple ops by pattern
parent().findChildren(type=TOP)     # All TOPs in parent
parent().findChildren(name='bg_*')  # By name pattern
```

## App Bootstrap Pattern

A `/project1` App extension manages global state:

```python
class App:
	def __init__(self, ownerComp: baseCOMP):
		self.ownerComp: baseCOMP = ownerComp
		# Load .env vars
		# Set up global references
		# Initialize subsystems

# Access globally:
op.App.Initialize()
```

Launch via shell script for reliable startup with environment variables.

## Refactoring Tips

- Extract repeated node patterns into reusable `.tox` components
- Use Select nodes to dynamically swap texture/data sources
- Collapse selected nodes into a Base COMP (right-click > Collapse Selected)
- Add a Null at the output for clean interfacing
- Store reusable components in the Palette (My Components folder)

## See Also

- [td-extension-template.md](td-extension-template.md) — Full extension template
- [td-replicator.md](td-replicator.md) — Replicator patterns
- [td-python-style.md](td-python-style.md) — Naming conventions
