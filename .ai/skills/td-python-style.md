---
name: td-python-style
description: Style guide for TouchDesigner Python code. Use this when cleaning up naming, typing, structure, and readability in TD scripts.
---

# TouchDesigner Python Style Guide

Coding conventions for Python in TouchDesigner projects.

## Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Classes | `PascalCase` | `class AppController:` |
| Public extension methods | `PascalCase` | `def GetCurrentState(self):` |
| Private extension methods | `camelCase` | `def getCurrentState(self):` |
| Utility functions (standalone .py) | `snake_case` | `def get_table_value(table, key):` |
| Constants | `UPPER_SNAKE_CASE` | `MODE_ATTRACT = 'attract'` |
| Private members | `camelCase`, no underscore | `self.isActive` |

**Special callback naming:**
```python
# AppStore toggle callbacks — don't rename these
def On_show(self):
def On_hide(self):
def On_will_show(self):
def On_showing(self):
def On_will_hide(self):
def On_hidden(self):
```

## Indentation

Use **tabs** (TouchDesigner convention), not spaces.

## Type Hints

Use Python type hints for clarity and IDE support. TD provides stub types.

```python
def __init__(self, ownerComp: baseCOMP) -> None:
	self.ownerComp: baseCOMP = ownerComp

def get_table_value(table: DAT, row: Union[int, str], col: Union[int, str]) -> Optional[str]:
	cell = table[row, col]
	return cell.val if cell else None

def set_parameter(comp: COMP, param_name: str, value: Union[int, float, str, bool]) -> None:
	comp.par[param_name] = value
```

Use specific sub-types when possible: `tableDAT`, `textDAT`, `baseCOMP`, `noiseTOP`, etc.

## Docstrings

Add docstrings to classes and public methods (skip for small, self-documenting functions):

```python
def process_data(self, data: dict) -> bool:
	"""
	Process incoming data and update state.

	Args:
		data: Dictionary containing the data to process

	Returns:
		True if processing succeeded, False otherwise
	"""
	pass
```

## String Formatting

Use f-strings:

```python
print(f"[{self.__class__.__name__}] Current state: {state}")
```

## Logging Pattern

Prefix logs with class/module name in brackets:

```python
print(f"[App] Initializing...")
print(f"[TableUtil] Row not found: {key}")
debug(f"[MyExtension] Value: {value}")  # TD debug — opens textport
```

## Section Headers

Group related methods with comment headers:

```python
###################################################
# Network Operations
###################################################

def ConnectNodes(self):
	...

def DisconnectAll(self):
	...
```

## Error Handling

```python
# Catch specific exceptions, not bare except
try:
	result = op(path)
except ValueError as e:
	print(f"[Error] Invalid value: {e}")

# Safe operator lookup
def safe_get_op(path: str) -> Optional[OP]:
	result = op(path)
	if result is None:
		print(f"[Warning] Operator not found: {path}")
	return result
```

## Anti-Patterns

```python
# BAD: repeated op() calls in loops
for i in range(100):
	op('/project1/data').appendRow([i])

# GOOD: cache the reference
data_table = op('/project1/data')
for i in range(100):
	data_table.appendRow([i])

# BAD: magic strings
if state == 'attract':

# GOOD: constants
MODE_ATTRACT = 'attract'
if state == MODE_ATTRACT:

# BAD: bare except
try:
	do_something()
except:
	pass

# GOOD: specific exception
try:
	do_something()
except ValueError as e:
	print(f"[Error] {e}")
```

## File Organization

```
project/
├── project.toe
└── python/
    ├── app/              # Extension classes (attached to COMPs)
    │   ├── App.py
    │   └── MyFeature.py
    ├── scripts/          # Standalone scripts
    │   └── requirements.txt
    └── util/             # Utility modules
        ├── __init__.py
        ├── table_util.py
        └── net/
```

- Extensions in `python/app/`
- Utilities in `python/util/`
- Import via `mod.module_name`

## Performance Tips

1. **Cache `op()` references** — don't call repeatedly in tight loops
2. **Batch table operations** — `clear()` + rebuild is faster than many individual edits
3. **Minimize `run()` calls** — prefer direct execution when possible
4. **Use `delayFrames`** over `delayMilliSeconds` for frame-accurate timing
5. **Avoid forcing cooks** — `cook(force=True)` should be rare

## IDE Setup

For external editing with autocomplete:
1. Point IDE to TD's Python: `C:\Program Files\Derivative\TouchDesigner\bin\python.exe`
2. Install TD stubs if available
3. Configure IDE to use tabs

## See Also

- [.ai/skills/td-extension-template.md](.ai/skills/td-extension-template.md) — Full extension boilerplate
- [.ai/skills/td-common-mistakes.md](.ai/skills/td-common-mistakes.md) — Common coding mistakes
- [python-cleanup prompt](.ai/prompts/python-cleanup.md) — AI prompt for code cleanup
