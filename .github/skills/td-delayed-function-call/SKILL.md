# Delayed Function Calls in TouchDesigner

Learn how to execute Python functions with delays in TouchDesigner using the `run()` command. This is essential for timing operations, sequencing events, and avoiding execution order issues.

## Overview

The `run()` command allows you to schedule Python code execution for a future time, specified in either frames or milliseconds. This is useful for:
- Delaying operations to avoid timing conflicts
- Creating sequences of events
- Working around parameter update order issues
- Triggering callbacks after a specific duration

[Official Documentation](https://derivative.ca/UserGuide/Run_Command_Examples)

## Basic run() Usage

Simple examples of calling functions with delays:

```python
# Call a global function with a delay
run("broadcastVals()", delayFrames=30)
# Call a function with an argument
run("TurnOff(args[0])", oldConnection, delayFrames=30)
# Call a script DAT with an argument and a delay
op('text_script_example').run('arg1=something', delayFrames=30)
```

## run() from Extensions

When calling `run()` from within an extension class, you can use various patterns:

```python
run(lambda: self.BroadcastVals(), delayMilliseconds=100)
run(self.BroadcastVals, delayFrames=30)
run('self.BroadcastVals(args)', delayFrames=30)
run( "args[0]()", lambda: self.update_par("dos"), delayFrames = 200 )  # https://forum.derivative.ca/t/using-run-to-delay-python-code-2022-12-11-15-37/306405/2
run("parent().SampleTriggerOff()", fromOP=me, delayFrames=1)
run(f"op('{self.ownerComp.path}').PulseTriggerLaunch()", delayFrames=delayFrames)
```

## Calling Functions from Other Text DATs

You can execute functions defined in other text DATs, either immediately or with a delay:

```python
op('text_other_script').module.function_name()
op('text_other_script').run('function_name()')	
op('text_other_script').run('function_name(args)', delayFrames=30)
op('text_other_script').run('function_name(args)', delayFrames=30, fromOP=me)
op('text_other_script').run('function_name(args)', delayFrames=30, fromOP=me, args=[arg1, arg2])
```

## Key Parameters

- `delayFrames`: Delay execution by a number of frames (timeline-dependent)
- `delayMilliseconds`: Delay execution by milliseconds (real-time)
- `fromOP`: Specify the operator context for the execution
- `args`: Pass arguments to the delayed function
