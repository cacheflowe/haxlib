from math import ceil
import td

def set_node_color(op: td.OP, r, g, b):
	op.color = (r, g, b)
	return


def get_node_color(op: td.OP):
	return op.color

def node_size_default_node():
	return (130, 90)

def node_size_default_base_comp():
	return (160, 130)

def get_node_size(op: td.OP):
	return (op.nodeWidth, op.nodeHeight)

def set_node_size(op: td.OP, width, height):
	op.nodeWidth = width
	op.nodeHeight = height
	return

def set_node_size_small(op: td.OP):
	origSize = node_size_default_node()
	set_node_size(op, origSize[0]/2, origSize[1]/2)
	return

def reset_node_size(op: td.OP):
	op.resetNodeSize()


def get_comp_children_by_type(comp: td.baseCOMP, nodeType):
	return nodes_of_type(nodes_in_comp(comp), nodeType)


def nodes_in_comp(comp: td.baseCOMP):
	nodes: list[td.OP] = comp.ops("*")
	return [op for op in nodes if op.parent() == comp]


def nodes_of_type(nodes: list[td.OP], opType):
	return [op for op in nodes if isinstance(op, opType)]


def get_downstream_ops(node: td.OP) -> list[td.OP]:
	"""Return all ops directly connected to node's outputs."""
	return list(node.outputs)


def get_all_downstream_ops(node: td.OP, _visited: set = None) -> list[td.OP]:
	"""Return all ops reachable downstream from node (recursive, no duplicates)."""
	if node is None:
		return []
	if _visited is None:
		_visited = set()
	_visited.add(node.id)
	result = [node]
	for op in node.outputs:
		if op.id not in _visited:
			result.extend(get_all_downstream_ops(op, _visited))
	return result


def set_node_collection_small(nodes: list[td.OP]):
	# usage: td_util.set_node_collection_small(td_util.get_all_downstream_ops(op('project1/lfo1')))
	for node in nodes:
		set_node_size_small(node)


def straighten_node_layout(node: td.OP, pad_x=10):
	# usage: td_util.straighten_node_layout(op('/project1/lfo1'))
	"""Straighten the layout of a node and its downstream connections."""
	downstream = get_all_downstream_ops(node)
	cur_x = node.nodeX
	starting_y = node.nodeY
	for i, op in enumerate(downstream):
		cur_x = ceil(cur_x / 25) * 25  # Round to nearest 25 for cleaner layout
		op.nodeX = cur_x
		cur_x += op.nodeWidth + pad_x
		op.nodeY = starting_y


def straighten_hovered_op():
	curOp: td.OP = td.ui.rolloverOp
	if curOp is None:
		return
	straighten_node_layout(curOp)


def print_op_tree(root: td.OP = None, max_depth: int = -1) -> None:
	"""Print a tree of all operators starting from root (defaults to project.root)."""
	if root is None:
		root = td.op('/')
	lines = [root.path or '/']
	_collect_op_tree(root, lines, '', 0, max_depth)
	print('\n'.join(lines))


def _collect_op_tree(node: td.OP, lines: list, prefix: str, depth: int, max_depth: int) -> None:
	if max_depth != -1 and depth >= max_depth:
		return
	children = node.children
	for i, child in enumerate(children):
		is_last = i == len(children) - 1
		lines.append(f'{prefix}{"└── " if is_last else "├── "}{child.name} [{child.type}]')
		_collect_op_tree(child, lines, prefix + ('    ' if is_last else '│   '), depth + 1, max_depth)

def get_network_editor() -> td.Pane:
	# assume first is the editor we're looking for
	for p in td.ui.panes:
		if p.type.name == 'NETWORKEDITOR':
			return p
	return None


def get_current_network() -> td.baseCOMP:
	"""Return the COMP currently displayed in a Network Editor pane (prefers the active pane), falling back to project root."""
	current = td.ui.panes.current
	if current is not None and current.type.name == 'NETWORKEDITOR':
		return current.owner
	pane = get_network_editor()
	if pane is not None:
		return pane.owner
	return td.op('/')



