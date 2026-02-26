# Delayed Function Calls in TouchDesigner

Schedule Python code execution for a future time using `run()`. Essential for timing operations, sequencing events, and avoiding execution-order issues.

## Documentation

- [Run Command Examples](https://derivative.ca/UserGuide/Run_Command_Examples)
- [Run Class](https://docs.derivative.ca/Run_Class)

## Basic Usage

```python
# Call a global function with a delay
run("broadcastVals()", delayFrames=30)

# Call a function with an argument via args[]
run("TurnOff(args[0])", oldConnection, delayFrames=30)

# Run a script DAT with arguments
op('text_script_example').run('arg1=something', delayFrames=30)

# Run at end of current frame
run("print('end of frame')", endFrame=True)

# Millisecond delay (real-time, not frame-dependent)
run("print('later')", delayMilliSeconds=1000)
```

## From Extensions

Several patterns for calling `run()` inside extension classes:

```python
# Lambda — cleanest for simple calls
run(lambda: self.BroadcastVals(), delayMilliSeconds=100)

# Direct method reference
run(self.BroadcastVals, delayFrames=30)

# String with self — works but less safe
run('self.BroadcastVals(args)', delayFrames=30)

# Lambda passed as arg — useful when self context might change
run("args[0]()", lambda: self.update_par("dos"), delayFrames=200)

# fromOP sets execution context (me = specified op)
run("parent().SampleTriggerOff()", fromOP=me, delayFrames=1)

# f-string with absolute path — safest for cross-component calls
run(f"op('{self.ownerComp.path}').PulseTriggerLaunch()", delayFrames=delayFrames)
```

## Cross-DAT Function Calls

Call functions defined in other Text DATs:

```python
# Immediate — via module import (preferred)
op('text_other_script').module.function_name()

# Immediate — via run
op('text_other_script').run('function_name()')

# Delayed with arguments
op('text_other_script').run('function_name(args[0])', myArg, delayFrames=30)

# Delayed with fromOP context
op('text_other_script').run('function_name()', fromOP=me, delayFrames=30)
```

## Key Parameters

| Parameter | Description |
|-----------|-------------|
| `delayFrames` | Delay by N frames (timeline-dependent) |
| `delayMilliSeconds` | Delay by N ms (real-time, wall clock) |
| `endFrame` | If `True`, execute at end of current frame |
| `fromOP` | Set execution context (`me` = this op inside the run) |
| `group` | Group name for organized script execution |
| `wallTime` | If `True`, use wall clock for delay timing |

## Cancel Pending Runs

```python
td.runs.clear()  # Cancel all pending runs
```

## Tips

- Prefer `delayFrames` for frame-accurate timing
- Prefer `delayMilliSeconds` for real-world timing (e.g., network timeouts)
- Use `fromOP=me` when the delayed code needs to reference `me` or `parent()`
- For extension methods, the lambda pattern `run(lambda: self.Method(), ...)` is the cleanest

## See Also

- [td-python-patterns.md](td-python-patterns.md) — General Python patterns
- [td-threading.md](td-threading.md) — Threading for long-running operations
