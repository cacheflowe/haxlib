## Replicator template snippets

Anchor replicants to the replicator parent by setting the Layout Origin props

```python
me.nodeX + 300
me.nodeY
```

```python
def onReplicate(comp, allOps, newOps, template, master):
	# get mixer & layout operators
	opDest = parent().op('merge1')

	for c in newOps:
		# set props to enable from disabled template
		c.par.display = 1
		c.par.enable = 1
		# connect to destination
		c.outputConnectors[0].connect(opDest)
		pass

	return
```
