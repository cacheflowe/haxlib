## Replicator template snippets

Anchor replicants to the replicator parent by setting the Layout Origin props

```python
me.nodeX + 300
me.nodeY
```

```python
def onReplicate(comp: replicatorCOMP, allOps: List[Any], newOps: List[Any], template: Any, master: Any):
	# template is often a tableDAT
	# Need to ignore the first row if it contains headers, but me.digits can help with that
	# if we're selecting row data per replicant
	template: tableDAT = template
	print('Building', template.numRows, 'clones')

	# master is often a baseCOMP
	master: baseCOMP = master

	# make connections
	opMerge: mathCHOP = op('math_merge_audio')
	
	# newOps is often a list of replicants created
	replicant: baseCOMP
	# for replicant in newOps:
	for i, replicant in enumerate(newOps):

		# set clone master param - keeps changes synced from master to replicants
		replicant.par.clone = comp.par.master

		# connect audio output
		replicant.outputConnectors[0].connect(opMerge)

		pass

	return

```
