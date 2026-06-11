---
name: td-snippets
description: Collection of small TouchDesigner Python snippets. Use this when you need quick utility examples or common one-off code patterns.
---

# TouchDesigner Python Snippets

Small, reusable code patterns for common TD tasks.

## Script CHOP — Create or Reuse a Channel

```python
if scriptOp['test1'] is None:
	scriptOp.appendChan('test1')
scriptOp['test1'][0] = 0.777
```

## Operator Connections

```python
# Read first input
op1.inputs[0]

# Connect operators
op1.outputConnectors[0].connect(op2)
op1.outputConnectors[0].connect(op2.inputConnectors[0])  # Explicit input

# Disconnect
op1.outputConnectors[0].disconnect()
```

## DAT Table — Concatenate to String

```python
# Join all rows of a 2-column table into "key: value" lines
"\n".join([f"{row[0]}: {row[1]}" for row in op('eval_props').rows()])
```

## Text TOP — Measure Text Width

```python
# Width of the Text TOP's current text
me.evalTextSize(me.par.text.eval())[0]

# Measure arbitrary text on a Text TOP
op('text_top').evalTextSize("text to measure")[0]
```

## Debugging

```python
debug(variable)          # TD debug — more info than print(), opens textport
dir(obj)                 # List all properties & methods of an object
print(repr(variable))    # Detailed representation
print(type(variable))    # Type of variable
```

## For Loops — Common Patterns

```python
for i in range(10):                    # Simple range
for i in range(maxResults):            # Variable limit
for item in collection:                # Direct iteration
for i, item in enumerate(collection):  # With index
for i in range(min(maxResults, len(items))):  # Capped iteration
for i, c in enumerate(newOps):         # Replicator pattern
for row in range(dat.numRows - 1, -1, -1):   # Loop backwards
```

## Date and Time

```python
from datetime import datetime

current_time = datetime.now()
formatted_time = current_time.strftime('%Y-%m-%d %H:%M:%S')
print("Current Date and Time:", formatted_time)
```

## String Formatting

```python
# Interpolation
f'var = {variable}'
'var = {}'.format(variable)

# Zero padding numbers
'{:03d}'.format(1)        # 001
'{:010d}'.format(9223)    # 0000009223

# Zero padding strings
'hi'.zfill(10)            # 0000000hi
'hi'.rjust(10, '0')       # 0000000hi

# Decimal precision
f'{val:.2f}'              # 2 decimal places
f'{val:.0f}'              # No decimal places
f'{val:05.2f}'            # 5 total chars, 2 decimals

# Thousand separators
f'{1234567:,}'            # 1,234,567
f'{1234567:_.2f}'         # 1_234_567.00

# Percentage
f'{0.123:.1%}'            # 12.3%
f'{0.5:.0%}'              # 50%

# Alignment
f'{text:<10}'             # Left align, 10 chars
f'{text:>10}'             # Right align
f'{text:^10}'             # Center align

# Hex / binary
f'{255:02x}'              # ff
f'{255:02X}'              # FF
f'{8:08b}'                # 00001000

# Truncation
f'{long_text:.10}'        # First 10 chars only

# Always show sign
f'{value:+.2f}'           # +3.14 or -3.14
```

## Working with Parameters

```python
# Pulse a parameter (button-type)
op('comp1').par.reset.pulse()

# Get parameter expression
expr = op('noise1').par.roughness.expr

# Check parameter mode
is_expr = op('noise1').par.roughness.mode == ParMode.EXPRESSION
```

## Expressions — Useful Globals

```python
me.digits        # Trailing number from operator name (e.g., 'noise3' -> 3)
me.name          # Operator name
me.path          # Full path
me.parent()      # Parent COMP
me.time.frame    # Current timeline frame
me.time.seconds  # Current timeline seconds
```

## See Also

- [.ai/skills/td-python-patterns.md](.ai/skills/td-python-patterns.md) — Larger code patterns by task
- [.ai/skills/td-common-mistakes.md](.ai/skills/td-common-mistakes.md) — Common mistakes to avoid
