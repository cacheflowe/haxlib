---
name: td-replicator
description: Replicator COMP patterns and callbacks for TouchDesigner. Use this when generating or updating replicants programmatically.
---

# Replicator Patterns in TouchDesigner

The Replicator COMP creates multiple copies of a template operator based on a data source (typically a table DAT). Think of it as a `for` loop that creates operator instances.

## Documentation

- [Replicator COMP](https://docs.derivative.ca/Replicator_COMP)

## Layout Anchoring

Anchor replicants relative to the replicator by setting Layout Origin parameter expressions:

```python
# Layout X: position replicants to the right of the replicator
me.nodeX + 300

# Layout Y: same vertical position
me.nodeY
```

## onReplicate Callback

The main callback for configuring newly created replicants:

```python
def onReplicate(comp: replicatorCOMP, allOps: list, newOps: list, template, master):
	# template is the data source (often a tableDAT)
	template: tableDAT = template
	print('Building', template.numRows, 'clones')

	# master is the template operator being cloned (often a baseCOMP)
	master: baseCOMP = master

	# Destination operator to connect outputs to
	opMerge: mathCHOP = op('math_merge_audio')

	# Configure each new replicant
	replicant: baseCOMP
	for i, replicant in enumerate(newOps):
		# Keep synced with master
		replicant.par.clone = comp.par.master

		# Enable (templates are often disabled)
		replicant.par.display = 1
		replicant.par.enable = 1

		# Connect output to a merge/composite
		replicant.outputConnectors[0].connect(opMerge)
```

## Simpler Callback

Minimal version that just connects replicants to a destination:

```python
def onReplicate(comp, allOps, newOps, template, master):
	opDest = parent().op('merge1')

	for c in newOps:
		c.par.display = 1
		c.par.enable = 1
		c.outputConnectors[0].connect(opDest)
```

## Accessing Row Data per Replicant

Each replicant's `me.digits` corresponds to its row index. Use this to pull per-instance data:

```python
# Inside a replicant's script or parameter expression
row_index = me.digits
value = op('table_source')[row_index, 'column_name'].val
```

Note: If the table has headers, `me.digits` starts at 1 (row 0 is headers). Adjust indexing accordingly.

## Tips

- Replicators are like `for` loops creating instances from a class (the master/template)
- Set `clone` parameter to keep replicants synced with the master template
- Templates are usually disabled — enable replicants in `onReplicate`
- Use `allOps` to access previously created replicants, `newOps` for newly created ones
- Replicants inherit the master's internal network, parameters, and extensions

## See Also

- [.ai/skills/td-oop.md](.ai/skills/td-oop.md) — OOP concepts (replicators as class instantiation)
- [.ai/skills/td-python-patterns.md](.ai/skills/td-python-patterns.md) — Creating/connecting operators
