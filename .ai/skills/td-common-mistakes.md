---
name: td-common-mistakes
description: TouchDesigner Python mistake-and-correction reference. Use this to avoid common TD API, parameter, and callback mistakes.
---

# TouchDesigner Python — Common Mistakes

Concrete mistake/correction pairs. Use this as an anti-hallucination reference when writing TD Python.

---

## 1. Importing `td`

**Wrong:**
```python
import td
import touchdesigner
```

**Correct:** `td`, `op`, `me`, `parent`, `ui`, `absTime` are pre-loaded globals. Never import them.

TD embeds its own Python interpreter. Standard library modules import normally, but to share code between DATs use `mod` (e.g., `mod.myModule.myFunction()`), not relative imports. Do not use `from td import *` or attempt to import TD globals from another module.

---

## 2. Inventing Parameter Names

**Wrong:**
```python
op('noise1').par.frequency       # Guessed — doesn't exist
op('moviefilein1').par.filename   # Guessed — actual name is 'file'
```

**Correct:** Parameter identifiers are the backtick names in the documentation (e.g., `roughness`, `resolutionw`, `file`). Always look them up — they are not consistently named and cannot be reliably guessed. For Text TOP font size, `par.fontsizex` is the canonical name; `par.fontsize` may exist as an alias in some builds, so verify on the parameter page.

---

## 3. Operator Dimensions via Parameters

**Wrong:**
```python
op('noise1').par.width
op('noise1').par.height
```

**Correct:**
```python
op('noise1').width     # Operator property — actual pixel width after cooking
op('noise1').height    # Operator property — actual pixel height
```

Resolution *parameters* exist (e.g., `par.resolutionw`, `par.resolutionh`) but they control the *requested* resolution. The `.width`/`.height` properties give you the *actual* cooked output dimensions.

---

## 4. DAT Cell Access with Double Indexing

**Wrong:**
```python
op('table1')[0][0]              # Python list-of-lists syntax — doesn't work
op('table1').row(0)[0]          # Not how TD works
```

**Correct:**
```python
op('table1')[0, 0].val          # Tuple indexing — row, col
op('table1')['name', 'col'].val # By header names
```

Always use `[row, col]` tuple syntax. Always append `.val` to read the cell's value as a string. To use it as a number, cast explicitly: `float(op('table1')[0, 0].val)` or `int(op('table1')[0, 0].val)`.

---

## 5. `.val` vs `.eval()`

**Common confusion:** `.val` and `.eval()` are treated as if they do completely different things when reading parameters.

**Correct:** For reading a parameter value, both `.val` and `.eval()` return the evaluated result. Prefer `.eval()` for clarity. The distinction matters when *setting*:

```python
# Reading — both work
op('noise1').par.roughness.eval()   # Preferred
op('noise1').par.roughness.val      # Also works

# Setting
op('noise1').par.roughness = 0.5        # Sets value
op('noise1').par.roughness.val = 0.5    # Same thing
op('noise1').par.roughness.expr = '...' # Sets expression string
```

`op()` returns `None` if the operator does not exist — it does not raise an exception. Always guard: `n = op('path'); if n is None: return`. Calling `.par`, `.width`, or any attribute on a `None` result raises `AttributeError`, not a TD-specific error.

---

## 6. Par Object Coercion

**Wrong:**
```python
result = round(op('noise1').par.roughness)      # Par object, not a number
x = op('noise1').par.tx + 10                    # Par + int — type error
```

**Correct:**
```python
result = round(op('noise1').par.roughness.eval())
x = op('noise1').par.tx.eval() + 10
```

`par.Name` returns a `Par` object, not a numeric value. Always call `.eval()` before arithmetic.

---

## 7. `me` Context Varies

**Wrong assumption:** `me` always refers to the same thing.

**Correct:** `me` depends on execution context:

| Context | `me` refers to |
|---------|---------------|
| Parameter expression | The operator owning the parameter |
| Text DAT script | The Text DAT itself |
| Execute DAT callback | The Execute DAT |
| Extension method | The COMP owning the extension |

Use explicit `op()` references when the context could be ambiguous.

---

## 8. Threading with TD Objects

**Wrong:**
```python
import threading
def worker():
    op('table1')[0, 0].val = 'updated'  # Crash or undefined behavior
threading.Thread(target=worker).start()
```

**Correct:** TouchDesigner operator access is **not thread-safe**. All operator reads/writes must happen on the main thread. For async work, use the global `run()` function with delays (not `td.run()`), or process data in the thread and pass results back via storage or a queue that the main thread reads. Violations of thread safety in TD often produce silent failures or non-deterministic crashes that do not surface as Python exceptions in the textport. If threading-related bugs are suspected, eliminate all `op()` access from worker threads as the first debugging step.

---

## 9. Pull-Based Cook Model

**Wrong assumption:** Setting a parameter immediately causes downstream operators to update.

**Correct:** TD uses a pull-based, demand-driven model. Operators only cook when their output is requested by something downstream (a viewer, a connected node, etc.). Setting a parameter marks the node dirty, but cooking happens later when demanded.

```python
op('noise1').par.roughness = 0.5
# noise1 has NOT cooked yet — it's just marked dirty
# It will cook when something downstream requests its output
```

To force immediate cooking: `op('noise1').cook(force=True)`.

---

## 10. GLSL Uniforms

**Wrong:** Assuming custom uniforms in a GLSL TOP are automatically available.

**Correct:** Custom uniforms must be declared in the shader AND the "Load Uniform Names" button must be pressed (or the parameter page refreshed) before uniform parameters appear on the operator. After loading, uniforms appear as parameters with their declared names.

---

## 11. Storing Operator References

**Wrong:**
```python
# In an extension __init__:
self.myNoise = op('noise1')     # Reference goes stale if op is deleted/renamed
```

**Correct:**
```python
# Look up fresh each time
def getNoiseValue(self):
    n = self.ownerComp.op('noise1')
    if n is not None:
        return n.par.roughness.eval()
```

Operator references can become invalid. For long-lived code, look up operators by path when needed, or guard against `None`.

---

## 12. Wrong Callback Signatures

**Wrong:**
```python
# CHOP Execute — missing parameters
def onValueChange(channel, val):
    pass

# Panel Execute — wrong parameters
def onOffToOn(panel, value, prev):
    pass
```

**Correct:** Callback signatures are exact. See [.ai/skills/td-python-patterns.md](.ai/skills/td-python-patterns.md) for the complete list. The three signatures below are illustrative only. Do not infer other callback signatures from these examples — always treat unlisted signatures as unknown and tell the user to verify in the documentation. Key signatures:

- CHOP Execute: `def onValueChange(channel, sampleIndex, val, prev)`
- Panel Execute: `def onOffToOn(panelValue)`
- DAT Execute: `def onTableChange(dat)`

---

## See Also

- [.ai/skills/td-skills.md](.ai/skills/td-skills.md) — Philosophy, retrieval strategy, class hierarchy
- [.ai/skills/td-python-patterns.md](.ai/skills/td-python-patterns.md) — Code patterns by task
