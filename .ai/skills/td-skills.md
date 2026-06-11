---
name: td-skills
description: Meta-skill for TouchDesigner AI assistance — TD philosophy, Python coding standards, documentation retrieval strategy, class hierarchy, and an index of all other TD skills. Use as a starting point when working on TD code or deciding which skill to consult.
---

# TouchDesigner AI Assistant Skills

This document provides context and best practices for AI coding assistants working with TouchDesigner projects.

## TouchDesigner Philosophy

### Pull-Based Architecture
TouchDesigner uses a **pull-based, demand-driven evaluation** model:
- Nodes only "cook" (evaluate) when their output is requested by a downstream node
- The viewer/output drives evaluation backward through the network
- Disconnected or unused branches don't cook, saving performance
- Understanding this helps explain why certain operations trigger updates and others don't

### Cook Optimization
- Minimize unnecessary cooking by structuring networks efficiently
- Use CHOPs and expressions for time-varying values rather than Python when possible
- Python scripts in DATs cook when their inputs change or when explicitly triggered
- The `me.cook(force=True)` method forces a node to re-evaluate

## Python Coding Standards in TouchDesigner

### Accessing Operators
```python
# Best practices for operator references
op('noise1')           # Relative path from current component
op('/project1/noise1') # Absolute path
op('../noise1')        # Relative path navigation

# Avoid storing operator references long-term
# The reference can become stale if the operator is deleted/renamed
myOp = op('noise1')  # OK for immediate use
```

### Parameter Access
```python
# Reading parameters
value = op('noise1').par.roughness.eval()  # Evaluate current value
value = op('noise1').par.roughness.val     # Same as .eval()

# Setting parameters
op('noise1').par.roughness = 0.5           # Direct assignment
op('noise1').par.roughness.val = 0.5       # Explicit value set
op('noise1').par.roughness.expr = "me.time.seconds"  # Set expression

# Parameter properties
op('noise1').par.roughness.mode            # ParMode.CONSTANT or ParMode.EXPRESSION
op('noise1').par.roughness.default         # Default value
op('noise1').par.roughness.min             # Minimum value
op('noise1').par.roughness.max             # Maximum value
```

### Operator-Specific Properties
Different operator types have specific properties:
```python
# TOPs - texture properties
op('noise1').width      # Pixel width
op('noise1').height     # Pixel height
op('noise1').aspect     # Width/height ratio

# CHOPs - channel data
op('constant1').numChans           # Number of channels
op('constant1').numSamples         # Number of samples
op('constant1')['chan1'].eval()    # Get channel value

# DATs - table data
op('table1').numRows              # Number of rows
op('table1').numCols              # Number of columns
op('table1')[0, 0].val            # Cell value by index
op('table1')['rowname', 'col']    # Cell by name
```

## Documentation Retrieval Strategy

When searching for information, consider:

1. **Operator Documentation**: For questions about specific node types (Noise TOP, Audio Device In CHOP, etc.)
   - Search: `search_touchdesigner_docs("Noise TOP")`
   - Contains: Parameters, inputs/outputs, usage examples

2. **Python Class Documentation**: For programmatic access patterns
   - Search: `get_python_class("moviefileinTOP")` or `search_touchdesigner_docs("TOP_Class Python")`
   - Contains: Methods, properties, Python API

3. **Dual Search for Complete Answers**: Many questions need BOTH
   - Example: "How do I load a video file with Python?"
   - Need: Movie File In TOP operator docs (parameters) AND Python class docs (API)

## Python Class Hierarchy

```
OP (base class for all operators)
├── TOP (texture operators)
│   ├── moviefileinTOP
│   ├── noiseTOP
│   └── ... (specific TOP types)
├── CHOP (channel operators)
│   ├── audiodeviceinCHOP
│   └── ...
├── DAT (data operators)
│   ├── tableDAT
│   ├── textDAT
│   └── ...
├── SOP (surface operators)
├── MAT (material operators)
└── COMP (component operators)
    ├── baseCOMP
    └── ...

Par (parameter class)
Cell (table cell class)
Channel (CHOP channel class)
```

## Common Pitfalls and Corrections

### Pitfall 1: Using Wrong Property for Dimensions
```python
# WRONG - these don't exist
op('moviefilein1').par.width   # Parameters, not actual dimensions
op('moviefilein1').par.height

# CORRECT - use operator properties for actual values
op('moviefilein1').width       # Actual pixel width after cooking
op('moviefilein1').height      # Actual pixel height
```

### Pitfall 2: Parameter vs. Evaluated Value
```python
# If parameter has an expression, .val returns the evaluated result
# To get the expression itself:
expr_string = op('noise1').par.roughness.expr

# To check if parameter is constant or expression:
is_expr = op('noise1').par.roughness.mode == ParMode.EXPRESSION
```

### Pitfall 3: DAT Cell Access
```python
# WRONG - mixing up rows/cols or using wrong accessor
op('table1')[0][0]            # This doesn't work as expected

# CORRECT - use proper cell access
op('table1')[0, 0].val        # By indices
op('table1')['rowName', 'colName'].val  # By names
```

### Pitfall 4: Script Execution Context
```python
# In different script contexts, 'me' refers to different things:
# - In a parameter expression: me = the operator with the parameter
# - In a Text DAT: me = the Text DAT itself
# - In an Execute DAT callback: me = the Execute DAT

# Use op() for explicit references when context might be ambiguous
```

## Best Practices for AI Assistance

1. **Always verify operator existence** before suggesting code that references specific operators
2. **Suggest using try/except** for operations that might fail (loading files, network ops)
3. **Recommend callbacks over polling** when waiting for events
4. **Consider cook order** when suggesting network structures
5. **Test parameter names** - TouchDesigner parameter names are case-sensitive and use camelCase

## See Also

### Python Reference
- [.ai/skills/td-python-patterns.md](.ai/skills/td-python-patterns.md) — Code patterns by task (DAT tables, CHOP channels, SOP geometry, extensions, storage, time)
- [.ai/skills/td-common-mistakes.md](.ai/skills/td-common-mistakes.md) — Mistake/correction pairs for anti-hallucination
- [.ai/skills/td-snippets.md](.ai/skills/td-snippets.md) — Small utility snippets (debugging, string formatting, connectors)
- [.ai/skills/td-python-style.md](.ai/skills/td-python-style.md) — Python coding conventions (naming, type hints, file org)
- [.ai/skills/td-delayed-calls.md](.ai/skills/td-delayed-calls.md) — `run()` patterns for delayed execution

### Architecture
- [.ai/skills/td-oop.md](.ai/skills/td-oop.md) — OOP concepts in TD (COMPs as classes, cloning, global refs)
- [.ai/skills/td-extension-template.md](.ai/skills/td-extension-template.md) — Full extension template with StorageManager and lifecycle
- [.ai/skills/td-replicator.md](.ai/skills/td-replicator.md) — Replicator COMP patterns
- [.ai/skills/td-wiring.md](.ai/skills/td-wiring.md) — Programmatic node wiring (connectors, multi-input, COMP connections)

### GLSL
- [.ai/skills/td-glsl.md](.ai/skills/td-glsl.md) — GLSL reference (built-in uniforms, functions, samplers, snippets)

### Environment and Infrastructure
- [.ai/skills/td-python-environment.md](.ai/skills/td-python-environment.md) — External modules (conda, venv, sys.path, tdPyEnvManager)
- [.ai/skills/td-threading.md](.ai/skills/td-threading.md) — Threading patterns (queues, subprocess, main-thread safety)
- [.ai/skills/td-ml.md](.ai/skills/td-ml.md) — Machine learning (ONNX, PyTorch, model repos)

### AI Prompts
- [.ai/prompts/python-cleanup.md](.ai/prompts/python-cleanup.md) — AI prompt for cleaning up TD Python code
- [.ai/prompts/glsl-cleanup.md](.ai/prompts/glsl-cleanup.md) — AI prompt for cleaning up TD GLSL code

### Learning
- [.ai/skills/td-resources.md](.ai/skills/td-resources.md) — Curated tutorials, YouTube channels, and references
