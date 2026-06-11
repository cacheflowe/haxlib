---
name: td-wiring
description: Programmatic node wiring patterns for TouchDesigner. Use this when connecting operators, managing inputs, or automating network wiring.
---

# TouchDesigner Node Wiring

Programmatically connect (wire) operators using Python. Covers single and multi-input/output operators, COMP-level connections, and type hints for the relevant classes.

## Python Type Hints

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from td import OP, COMP, Connector
```

### Key Classes

| Class       | Description                                        |
|-------------|----------------------------------------------------|
| `OP`        | Base class for all operators                       |
| `COMP`      | Component operator (has top/bottom connectors)     |
| `Connector` | A single input or output connection point on a node|

### Connector Members (Read Only)

```python
connector.index        # int   — numeric index on the node
connector.isInput      # bool  — True if input connector
connector.isOutput     # bool  — True if output connector
connector.owner        # OP    — the node this connector belongs to
connector.connections  # list[Connector] — connected counterparts
connector.description  # str   — e.g. 'Color Image', 'Depth'
connector.inOP         # OP | None — associated In OP (COMP passthrough)
connector.outOP        # OP | None — associated Out OP (COMP passthrough)
```

## OP Connection Members (left/right wires)

```python
n: OP = op('myNode')

n.inputs              # list[OP]        — input operators
n.outputs             # list[OP]        — output operators
n.inputConnectors     # list[Connector] — input connector objects
n.outputConnectors    # list[Connector] — output connector objects

n.minInputs           # int  — minimum required inputs
n.maxInputs           # int  — maximum allowed inputs
n.isMultiInputs       # bool — True if inputs are unordered (e.g. Merge)
n.isFilter            # bool — True if node has inputs; False if generator
```

## COMP Connection Members (top/bottom wires)

```python
c: COMP = op('myComp')

c.inputCOMPs              # list[COMP]      — components wired into the top
c.outputCOMPs             # list[COMP]      — components wired out the bottom
c.inputCOMPConnectors     # list[Connector] — top connectors
c.outputCOMPConnectors    # list[Connector] — bottom connectors
```

## Connecting Operators

### Basic — Output to Next Node

```python
# Connect noise1's output → lag1's first input
op('noise1').outputConnectors[0].connect(op('lag1'))
```

### Specific Input Index (multi-input nodes)

Many operators accept multiple inputs with distinct roles.

```python
# Displace TOP: input 0 = source image, input 1 = displacement map
op('moviefilein1').outputConnectors[0].connect(
    op('displace1').inputConnectors[0]   # source
)
op('noise1').outputConnectors[0].connect(
    op('displace1').inputConnectors[1]   # displacement
)

# Composite TOP: any number of ordered inputs
op('moviefilein1').outputConnectors[0].connect(
    op('comp1').inputConnectors[0]
)
op('moviefilein2').outputConnectors[0].connect(
    op('comp1').inputConnectors[1]
)
```

### Merge-style (variable number of unordered inputs)

```python
# Merge CHOP / Merge SOP accept arbitrary inputs
op('wave1').outputConnectors[0].connect(op('merge1'))
op('wave2').outputConnectors[0].connect(op('merge1'))
```

### Batch-set all inputs at once

```python
# OP.setInputs() replaces ALL inputs in one call
# Use None to leave a slot disconnected
op('displace1').setInputs([op('moviefilein1'), op('noise1')])

# Disconnect all inputs
op('displace1').setInputs([])
```

### COMP-to-COMP (top/bottom connectors)

```python
# Connect geo1's bottom → geo2's top (equivalent methods)
op('geo1').outputCOMPConnectors[0].connect(op('geo2'))
op('geo2').inputCOMPConnectors[0].connect(op('geo1'))
```

## Disconnecting

```python
# Disconnect a specific input/output connector
op('lag1').inputConnectors[0].disconnect()
op('lag1').outputConnectors[0].disconnect()

# Disconnect COMP connectors
op('geo1').outputCOMPConnectors[0].disconnect()
op('geo2').inputCOMPConnectors[0].disconnect()
```

## Inspecting Connections

```python
n: OP = op('displace1')

# List what's connected to each input
for i, conn in enumerate(n.inputConnectors):
    linked: list[Connector] = conn.connections
    names = [c.owner.name for c in linked]
    print(f'Input {i} ({conn.description}): {names}')

# Walk upstream from a node
def walk_upstream(node: OP, depth: int = 0) -> None:
    indent = '  ' * depth
    print(f'{indent}{node.name} ({node.opType})')
    for inp in node.inputs:
        if inp is not None:
            walk_upstream(inp, depth + 1)

walk_upstream(op('null1'))
```

## Common Multi-Input Operators

| Operator       | Input 0          | Input 1          | Input 2+              |
|----------------|------------------|------------------|-----------------------|
| Displace TOP   | Source image     | Displacement map | —                     |
| Composite TOP  | Background       | Foreground(s)    | Additional layers     |
| Over TOP       | Input 1          | Input 2          | —                     |
| Cross TOP      | Input A          | Input B          | —                     |
| Switch TOP     | First option     | Second option    | More options          |
| Feedback TOP   | Source           | Target           | —                     |
| GLSL TOP       | Sampler 0        | Sampler 1        | More samplers         |
| Merge CHOP/SOP | Any (unordered)  | Any              | Any                   |
| Math CHOP      | Input 1          | Input 2          | More inputs           |
| Boolean SOP    | SOP A            | SOP B            | —                     |
| Transform SOP  | Source geometry  | —                | —                     |

## Building a Chain Programmatically

```python
def build_chain(
    parent_comp: COMP,
    op_types: list[type],
    start_name: str = 'node'
) -> list[OP]:
    """Create a chain of operators and wire them sequentially."""
    nodes: list[OP] = []
    for i, op_type in enumerate(op_types):
        n: OP = parent_comp.create(op_type, f'{start_name}{i}')
        n.nodeX = i * 200
        if nodes:
            nodes[-1].outputConnectors[0].connect(n)
        nodes.append(n)
    parent_comp.layout(nodes, horizontal=True)
    return nodes

# Example: build a TOP chain
chain = build_chain(
    op('/project1'),
    [moviefileinTOP, levelTOP, blurTOP, nullTOP],
    start_name='pipeline'
)
```

## Creating and Wiring in One Pattern

```python
parent: COMP = op('/project1')

# Create nodes
noise: OP  = parent.create(noiseTOP, 'noise_src')
blur: OP   = parent.create(blurTOP, 'blur_pass')
level: OP  = parent.create(levelTOP, 'level_adj')
comp: OP   = parent.create(compositeTOP, 'comp_out')
bg: OP     = parent.create(constantTOP, 'bg_color')

# Wire the chain
noise.outputConnectors[0].connect(blur)
blur.outputConnectors[0].connect(level)

# Composite: bg on input 0, processed image on input 1
bg.outputConnectors[0].connect(comp.inputConnectors[0])
level.outputConnectors[0].connect(comp.inputConnectors[1])

# Layout
parent.layout([noise, blur, level], horizontal=True)
```

## Tips

- **Input connectors replace**: calling `connect()` on an *input* connector replaces its existing connection
- **Output connectors append**: calling `connect()` on an *output* connector adds a new wire
- Use `connector.description` to discover what each input slot expects (e.g. `'Color Image'`, `'Depth'`)
- Use `n.maxInputs` and `n.isMultiInputs` to check wiring constraints before connecting
- COMP top/bottom connectors are separate from the operator's left/right connectors
- `setInputs([...])` is the safest way to rewire all inputs atomically

## See Also

- [.ai/skills/td-snippets.md](.ai/skills/td-snippets.md) — Small utility snippets including basic connector examples
- [.ai/skills/td-python-patterns.md](.ai/skills/td-python-patterns.md) — Larger code patterns by task
- [.ai/skills/td-oop.md](.ai/skills/td-oop.md) — OOP concepts with COMPs as classes
- [.ai/skills/td-replicator.md](.ai/skills/td-replicator.md) — Replicator COMP patterns (dynamic node creation)
- [.ai/skills/td-skills.md](.ai/skills/td-skills.md) — Master skill index
