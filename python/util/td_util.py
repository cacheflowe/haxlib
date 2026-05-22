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
	