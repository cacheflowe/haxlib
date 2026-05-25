import td

def set_node_color(op: td.OP, r, g, b):
	op.color = (r, g, b)
	return


def get_node_color(op: td.OP):
	return op.color


def set_node_size(op: td.OP, width, height):
	op.nodeWidth = width
	op.nodeHeight = height
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
	