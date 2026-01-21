## Script OPs

Create or reuse a channel:

```python
if scriptOp['test1'] is None:
	scriptOp.appendChan('test1')
scriptOp['test1'][0] = 0.777
```

## Date/time

```python
from datetime import datetime

current_time = datetime.now()
formatted_time = current_time.strftime('%Y-%m-%d %H:%M:%S')
print("Current Date and Time:", formatted_time)
```

## Concat a table DAT into a single line

```python
"\n".join([f"{row[0]}: {row[1]}" for row in op('eval_props').rows()])
```

## Op connectors

```python
op.inputs[0]
op1.outputConnectors[0].connect(op2)
op1.outputConnectors[0].connect(op2.inputConnectors[0])
```


## Get text width

```python
me.evalTextSize(me.par.text.eval())[0]
op('text_top').evalTextSize("text to measure")[0]
```

## Debugging

```python
debug(variable) # TouchDesigner debug print - provides more info than print()
dir(newTuplet) # list all properties & methods of an object
print(repr(variable)) # detailed representation of a variable	
print(type(variable)) # type of variable
```
