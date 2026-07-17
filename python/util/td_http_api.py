import io
import json
import os
import re
import sys
import time
import traceback

# ---------------------------------------------------------------------------
# Network description (self-contained — no td_util dependency, so this file
# can be dropped into any project as a single Callbacks DAT).
# ---------------------------------------------------------------------------

def _get_current_network():
	"""Return the COMP currently displayed in a Network Editor pane (prefers the active pane), falling back to project root."""
	current = ui.panes.current
	if current is not None and current.type.name == 'NETWORKEDITOR':
		return current.owner
	for p in ui.panes:
		if p.type.name == 'NETWORKEDITOR':
			return p.owner
	return op('/')


def _get_network_editor_pane():
	"""Return the NetworkEditor pane object itself (not its owner) — prefers the active pane."""
	current = ui.panes.current
	if current is not None and current.type.name == 'NETWORKEDITOR':
		return current
	for p in ui.panes:
		if p.type.name == 'NETWORKEDITOR':
			return p
	return None


def _nodes_in_comp(comp):
	return comp.findChildren(depth=1, includeUtility=True)


def _par_json_value(par):
	"""Serialize a parameter's evaluated value into something JSON-safe (OPs become their path)."""
	if par.isOP:
		vals = par.eval()
		if vals is None:
			return None
		if isinstance(vals, list):
			return [v.path for v in vals]
		return vals.path
	try:
		return par.eval()
	except Exception:
		return str(par.val)


def _describe_par(par):
	"""JSON-safe snapshot of a single parameter's current state: name, mode, evaluated value, and expr if applicable."""
	entry = {'name': par.name, 'mode': par.mode.name, 'value': _par_json_value(par)}
	if par.mode.name == 'EXPRESSION':
		entry['expr'] = par.expr
	return entry


def _get_customized_pars(target):
	"""Return {parName: {mode, value, [expr]}} for params that differ from default, mirroring the params dialog's 'Show Custom Only' view."""
	result = {}
	for par in target.pars('*'):
		if par.isDefault or par.hidden:
			continue
		entry = _describe_par(par)
		del entry['name']
		result[par.name] = entry
	return result


_OP_EXPR_PATTERN = re.compile(r"\bop(?:ex)?\(\s*['\"]([^'\"]+)['\"]")


def _get_op_references(target):
	"""Return dashed-line style references from target to other ops: OP-type params, binds, exports,
	and op()/opex() calls found inside expression-mode parameters."""
	refs = []
	seen = set()

	def add(candidate, kind, par_name):
		if candidate is None or not candidate.valid or candidate is target:
			return
		key = (candidate.path, kind, par_name)
		if key in seen:
			return
		seen.add(key)
		refs.append({'from': target.path, 'to': candidate.path, 'kind': kind, 'par': par_name})

	for par in target.pars('*'):
		if par.hidden or par.isDefault:
			continue
		if par.isOP:
			vals = par.eval()
			for candidate in (vals if isinstance(vals, list) else ([vals] if vals else [])):
				add(candidate, 'opParam', par.name)
		if par.bindMaster:
			add(par.bindMaster, 'bind', par.name)
		if par.exportOP:
			add(par.exportOP, 'export', par.name)
		if par.mode.name == 'EXPRESSION' and par.expr:
			expr_root = target.parent() or target
			for m in _OP_EXPR_PATTERN.finditer(par.expr):
				add(expr_root.op(m.group(1)), 'expression', par.name)

	return refs


def _get_wires(nodes):
	"""Return wired (solid line) connections among the given nodes as {from, to, toInput} dicts."""
	node_paths = {n.path for n in nodes}
	wires = []
	for node in nodes:
		for idx, src in enumerate(node.inputs):
			if src is not None and src.path in node_paths:
				wires.append({'from': src.path, 'to': node.path, 'toInput': idx})
	return wires


def describe_network(comp=None, recursive=False):
	"""Build a lightweight structural map of a network: nodes, wired connections, dashed-line
	references, and customized (non-default) parameters. Node/wire/reference lists are sorted
	deterministically so repeated calls diff cleanly."""
	if comp is None:
		comp = _get_current_network()
	nodes = comp.findChildren(includeUtility=True) if recursive else _nodes_in_comp(comp)

	node_entries = []
	references = []
	for node in nodes:
		entry = {
			'path': node.path,
			'name': node.name,
			'opType': node.opType,
			'family': node.family,
			'nodeX': node.nodeX,
			'nodeY': node.nodeY,
			'nodeWidth': node.nodeWidth,
			'nodeHeight': node.nodeHeight,
		}
		if node.comment:
			entry['comment'] = node.comment
		if node.opType == 'annotateCOMP':
			entry['enclosedOPs'] = sorted(n.path for n in node.enclosedOPs)
		custom = _get_customized_pars(node)
		if custom:
			entry['customPars'] = custom
		node_entries.append(entry)
		references.extend(_get_op_references(node))

	node_entries.sort(key=lambda e: e['path'])
	references.sort(key=lambda r: (r['from'], r['to'], r['kind'], r['par']))
	wires = _get_wires(nodes)
	wires.sort(key=lambda w: (w['to'], w['toInput']))

	return {
		'root': comp.path,
		'nodes': node_entries,
		'wires': wires,
		'references': references,
	}


def _mermaid_id(path):
	return re.sub(r'\W', '_', path)


def network_to_mermaid(comp=None, recursive=False):
	"""Render describe_network() as a Mermaid flowchart: solid arrows for wires, dashed arrows for references."""
	data = describe_network(comp, recursive)
	lines = ['flowchart TD']
	for node in data['nodes']:
		node_id = _mermaid_id(node['path'])
		label = f"{node['name']}\\n[{node['opType']}]"
		if 'customPars' in node:
			label += f"\\nΔ{len(node['customPars'])}"
		lines.append(f'\t{node_id}["{label}"]')
	for wire in data['wires']:
		lines.append(f"\t{_mermaid_id(wire['from'])} --> {_mermaid_id(wire['to'])}")
	for ref in data['references']:
		lines.append(f"\t{_mermaid_id(ref['from'])} -.->|{ref['kind']}| {_mermaid_id(ref['to'])}")
	return '\n'.join(lines)


def _diff_nodes(before_nodes, after_nodes):
	before_by_path = {n['path']: n for n in before_nodes}
	after_by_path = {n['path']: n for n in after_nodes}
	added = sorted(set(after_by_path) - set(before_by_path))
	removed = sorted(set(before_by_path) - set(after_by_path))
	changed = []
	for path in sorted(set(before_by_path) & set(after_by_path)):
		b, a = before_by_path[path], after_by_path[path]
		node_changes = {}
		for key in ('nodeX', 'nodeY', 'nodeWidth', 'nodeHeight', 'opType', 'family', 'name'):
			if b.get(key) != a.get(key):
				node_changes[key] = {'before': b.get(key), 'after': a.get(key)}
		b_pars = b.get('customPars', {})
		a_pars = a.get('customPars', {})
		par_added = sorted(set(a_pars) - set(b_pars))
		par_removed = sorted(set(b_pars) - set(a_pars))
		par_changed = sorted(p for p in (set(a_pars) & set(b_pars)) if a_pars[p] != b_pars[p])
		if par_added or par_removed or par_changed:
			node_changes['customPars'] = {
				'added': {p: a_pars[p] for p in par_added},
				'removed': {p: b_pars[p] for p in par_removed},
				'changed': {p: {'before': b_pars[p], 'after': a_pars[p]} for p in par_changed},
			}
		if node_changes:
			changed.append({'path': path, 'changes': node_changes})
	return {'added': added, 'removed': removed, 'changed': changed}


def _diff_edges(before_edges, after_edges, key_fields):
	def key(e):
		return tuple(e[f] for f in key_fields)
	before_by_key = {key(e): e for e in before_edges}
	after_by_key = {key(e): e for e in after_edges}
	added = [after_by_key[k] for k in sorted(after_by_key.keys() - before_by_key.keys())]
	removed = [before_by_key[k] for k in sorted(before_by_key.keys() - after_by_key.keys())]
	return {'added': added, 'removed': removed}


def diff_networks(before, after):
	"""Structural diff between two describe_network() snapshots: added/removed/changed nodes,
	and added/removed wires and references. Both inputs must be full snapshot dicts, not paths."""
	return {
		'nodes': _diff_nodes(before.get('nodes', []), after.get('nodes', [])),
		'wires': _diff_edges(before.get('wires', []), after.get('wires', []), ('from', 'to', 'toInput')),
		'references': _diff_edges(before.get('references', []), after.get('references', []), ('from', 'to', 'kind', 'par')),
	}


# ---------------------------------------------------------------------------
# HTTP request helpers
# ---------------------------------------------------------------------------

class MethodNotAllowedError(Exception):
	pass


def _first_param(pars, name, default=None):
	"""pars values may arrive as a list (repeated query params) or a bare string; normalize to a single value."""
	val = pars.get(name, default)
	if isinstance(val, list):
		return val[0] if val else default
	return val


def _bool_param(pars, name, default=False):
	val = _first_param(pars, name)
	if val is None:
		return default
	return val.lower() in ('1', 'true', 'yes')


def _resolve_comp(pars):
	path = _first_param(pars, 'path')
	if not path:
		return None  # let describe_network default to the currently open network
	target = op(path)
	if target is None:
		raise ValueError(f"no operator found at path '{path}'")
	return target


def _resolve_op(path):
	if not path:
		raise ValueError("missing required 'path' query parameter")
	target = op(path)
	if target is None:
		# Try to resolve utility nodes by looking up parent and finding child including utilities
		parent_path = os.path.dirname(path).replace('\\', '/')
		name = os.path.basename(path)
		parent = op(parent_path) if parent_path else None
		if parent is not None:
			found = parent.findChildren(name=name, depth=1, includeUtility=True)
			if found:
				target = found[0]
	if target is None:
		raise ValueError(f"no operator found at path '{path}'")
	return target


def _coerce_par_value(par, raw):
	"""Convert a raw query-string value into whatever type the parameter actually expects."""
	if par.isToggle:
		return raw.lower() in ('1', 'true', 'yes', 'on')
	if par.isInt:
		return int(float(raw))
	if par.isFloat:
		return float(raw)
	if par.isOP:
		target = op(raw)
		if target is None:
			raise ValueError(f"no operator found at path '{raw}' for OP-type parameter")
		return target
	return raw


def _resolve_inputs(raw):
	if not raw:
		return []
	result = []
	for p in raw.split(','):
		p = p.strip()
		if not p:
			continue
		target = op(p)
		if target is None:
			raise ValueError(f"no operator found at path '{p}' for input")
		result.append(target)
	return result


def _node_summary(n):
	return {
		'path': n.path, 'name': n.name, 'opType': n.opType, 'family': n.family,
		'nodeX': n.nodeX, 'nodeY': n.nodeY, 'nodeWidth': n.nodeWidth, 'nodeHeight': n.nodeHeight,
		'viewer': n.viewer,
	}


def _op_error_state(n):
	return {'path': n.path, 'name': n.name, 'opType': n.opType, 'errors': n.errors(), 'warnings': n.warnings()}


_IMAGE_MIME_TYPES = {
	'.png': 'image/png',
	'.jpg': 'image/jpeg',
	'.jpeg': 'image/jpeg',
	'.bmp': 'image/bmp',
	'.tif': 'image/tiff',
	'.tiff': 'image/tiff',
	'.exr': 'image/x-exr',
	'.dds': 'image/vnd-ms-dds',
}


def _chop_data(chop, max_samples=100):
	"""Most-recent max_samples samples of every channel in a CHOP, plus rate/count metadata."""
	n = min(chop.numSamples, max_samples) if max_samples else chop.numSamples
	start = chop.numSamples - n
	channels = {}
	for c in chop.chans():
		channels[c.name] = [c[i] for i in range(start, chop.numSamples)]
	return {
		'numChans': chop.numChans,
		'numSamples': chop.numSamples,
		'samplesReturned': n,
		'rate': chop.rate,
		'channels': channels,
	}


def _snapshot_top(top, filetype='.png', quality=1.0):
	"""Render a TOP's current frame to an in-memory image (no disk write) via TOP.saveByteArray().
	Returns (bytearray, mimeType)."""
	if filetype not in _IMAGE_MIME_TYPES:
		raise ValueError(f"unsupported snapshot format '{filetype}'. Supported: {sorted(_IMAGE_MIME_TYPES)}")
	data = top.saveByteArray(filetype, quality=quality)
	return data, _IMAGE_MIME_TYPES[filetype]


def _bounds_of(nodes):
	"""Aggregate bounding box of a list of ops, in network-editor units. nodeX/nodeY anchor each
	node's left/bottom corner (TD convention), so the box extends right/up by width/height."""
	min_x = min(n.nodeX for n in nodes)
	min_y = min(n.nodeY for n in nodes)
	max_x = max(n.nodeX + n.nodeWidth for n in nodes)
	max_y = max(n.nodeY + n.nodeHeight for n in nodes)
	return {
		'minX': min_x, 'minY': min_y, 'maxX': max_x, 'maxY': max_y,
		'width': max_x - min_x, 'height': max_y - min_y,
		'count': len(nodes),
		'nodes': sorted(n.path for n in nodes),
	}


def _rects_overlap(x, y, w, h, n):
	return not (x + w <= n.nodeX or n.nodeX + n.nodeWidth <= x or y + h <= n.nodeY or n.nodeY + n.nodeHeight <= y)


def _create_annotation(parent, nodes, title='', body='', mode='networkbox', pad=40, title_height=30):
	"""Create an annotateCOMP sized to enclose the given nodes' bounding box (plus padding, and
	extra headroom for the title bar), with encloseops on so moving it later drags the group with it."""
	box = _bounds_of(nodes)
	annotation = parent.create('annotateCOMP')
	annotation.viewer = True
	annotation.nodeX = box['minX'] - pad
	annotation.nodeY = box['minY'] - pad
	annotation.nodeWidth = box['width'] + 2 * pad
	annotation.nodeHeight = box['height'] + 2 * pad + title_height
	annotation.par.Mode = mode
	if title:
		annotation.par.Titletext = title
	if body:
		annotation.par.Bodytext = body
	annotation.par.encloseops = True
	return annotation


def _auto_place(parent, inputs, exclude=None, width=130, height=90, pad_x=70, pad_y=20):
	"""Placement for a new node when x/y aren't given: to the right of (and vertically averaged
	with) its inputs, following dataflow left-to-right; falls back to right of existing siblings
	if there are no inputs. Nudges down to clear any overlap with existing nodes in the comp."""
	siblings = [n for n in _nodes_in_comp(parent) if n is not exclude]
	if inputs:
		x = max(n.nodeX + n.nodeWidth for n in inputs) + pad_x
		y = sum(n.nodeY for n in inputs) / len(inputs)
	elif siblings:
		x = max(n.nodeX + n.nodeWidth for n in siblings) + pad_x
		y = min(n.nodeY for n in siblings)
	else:
		x, y = 0, 0
	attempts = 0
	while attempts < 50 and any(_rects_overlap(x, y, width, height, n) for n in siblings):
		y -= height + pad_y
		attempts += 1
	return x, y


def _require_write_method(request, uri):
	if request['method'] not in ('POST', 'PUT'):
		raise MethodNotAllowedError(f"{uri} requires POST or PUT")


# ---------------------------------------------------------------------------
# Templates — reusable network patterns stored as JSON under data/harness/network-templates/.
# See data/harness/network-templates/simple_feedback_loop.json for the schema by example.
# ---------------------------------------------------------------------------

def _load_template(name):
	if not name or '/' in name or '\\' in name or '..' in name:
		raise ValueError(f"invalid template name '{name}'")
	path = os.path.join(project.folder, 'data', 'harness', 'network-templates', f'{name}.json')
	if not os.path.isfile(path):
		raise ValueError(f"template '{name}' not found at {path}")
	with open(path, 'r') as f:
		return json.load(f)


def _resolve_slots(template, pars):
	resolved = {}
	for slot_name, slot_spec in template.get('slots', {}).items():
		raw = _first_param(pars, slot_name)
		if raw is None:
			raw = slot_spec.get('default')
		if raw is None:
			raise ValueError(f"missing required slot '{slot_name}' ({slot_spec.get('description', 'no description')})")
		resolved[slot_name] = raw
	return resolved


def _apply_template_par(par, spec, name_to_op, slot_values):
	if 'value' in spec:
		par.val = spec['value']
	elif 'expr' in spec:
		par.expr = spec['expr']
	elif 'ref' in spec:
		target = name_to_op.get(spec['ref'])
		if target is None:
			raise ValueError(f"template references unknown node '{spec['ref']}'")
		par.val = target
	elif 'slot' in spec:
		slot_name = spec['slot']
		if slot_name not in slot_values:
			raise ValueError(f"template par references unknown slot '{slot_name}'")
		par.val = slot_values[slot_name]
	else:
		raise ValueError(f"unrecognized par spec {spec!r}")


def instantiate_template(template, parent, x_offset=0.0, y_offset=0.0, name_prefix='', slot_values=None):
	"""Create every node/par/wire described by a loaded template inside parent, offset by
	(x_offset, y_offset). Returns {templateLocalName: createdOp}."""
	slot_values = slot_values or {}
	name_to_op = {}
	for node_spec in template['nodes']:
		new_node = parent.create(node_spec['opType'], f"{name_prefix}{node_spec['name']}")
		new_node.viewer = True
		new_node.nodeX = x_offset + node_spec.get('x', 0)
		new_node.nodeY = y_offset + node_spec.get('y', 0)
		name_to_op[node_spec['name']] = new_node

	for node_spec in template['nodes']:
		target = name_to_op[node_spec['name']]
		for par_name, par_spec in node_spec.get('pars', {}).items():
			par = target.par[par_name]
			if par is None:
				raise ValueError(f"node '{node_spec['name']}' ({node_spec['opType']}) has no parameter '{par_name}'")
			_apply_template_par(par, par_spec, name_to_op, slot_values)

	inputs_by_target = {}
	for wire in template.get('wires', []):
		inputs_by_target.setdefault(wire['to'], {})[wire['toInput']] = name_to_op[wire['from']]
	for to_name, index_map in inputs_by_target.items():
		target = name_to_op[to_name]
		ordered = [index_map.get(i) for i in range(max(index_map) + 1)]
		target.setInputs(ordered)

	return name_to_op


# ---------------------------------------------------------------------------
# Request logging — in-memory ring buffer, readable via GET /logs.
# Resets on /reload (module-level state), which is fine for a debugging aid.
# ---------------------------------------------------------------------------

_REQUEST_LOG = []
_REQUEST_LOG_MAX = 200


def _log_request(entry):
	_REQUEST_LOG.append(entry)
	del _REQUEST_LOG[:-_REQUEST_LOG_MAX]


# ---------------------------------------------------------------------------
# Route handlers — one function per URI. Each receives (request, response, pars)
# and writes statusCode / content-type / data into response. webServerDAT is
# passed only where needed (health, run).
# ---------------------------------------------------------------------------

def _ok_json(response, data):
	response['statusCode'] = 200
	response['statusReason'] = 'OK'
	response['content-type'] = 'application/json'
	response['data'] = json.dumps(data)

def _ok_json_sorted(response, data):
	response['statusCode'] = 200
	response['statusReason'] = 'OK'
	response['content-type'] = 'application/json'
	response['data'] = json.dumps(data, sort_keys=True, indent=2)

def _ok_text(response, text):
	response['statusCode'] = 200
	response['statusReason'] = 'OK'
	response['content-type'] = 'text/plain'
	response['data'] = text


def _route_network(request, response, pars, **_):
	comp = _resolve_comp(pars)
	recursive = _bool_param(pars, 'recursive')
	_ok_json_sorted(response, describe_network(comp, recursive))


def _route_network_mmd(request, response, pars, **_):
	comp = _resolve_comp(pars)
	recursive = _bool_param(pars, 'recursive')
	_ok_text(response, network_to_mermaid(comp, recursive))


def _route_selected(request, response, pars, **_):
	comp_path = _first_param(pars, 'path')
	comp = _resolve_op(comp_path) if comp_path else _get_current_network()
	_ok_json(response, [_node_summary(n) for n in comp.selectedChildren])


def _route_select(request, response, pars, **_):
	"""Set the TD UI's node selection (and optionally home the network editor on it) so an
	agent can direct the user's attention to specific nodes — the write-side mirror of /selected."""
	_require_write_method(request, '/select')
	paths_param = _first_param(pars, 'paths') or _first_param(pars, 'path')
	if not paths_param:
		raise ValueError("missing required 'path' or 'paths' query parameter")
	nodes = [_resolve_op(p.strip()) for p in paths_param.split(',') if p.strip()]
	parent = nodes[0].parent()
	for child in _nodes_in_comp(parent):
		if child.selected:
			child.selected = False
	for n in nodes:
		n.selected = True
	nodes[0].current = True
	if _bool_param(pars, 'home', True):
		pane = _get_network_editor_pane()
		if pane is not None:
			pane.owner = parent
			pane.homeSelected(zoom=_bool_param(pars, 'zoom', True))
	_ok_json(response, [_node_summary(n) for n in nodes])


def _route_insert(request, response, pars, **_):
	"""Splice a new node into an existing connection: create opType, wire the current source of
	dest's input into it, and wire it into dest — shifting dest and everything to its right to
	make room. Identifies the connection by dest 'path' + 'input' index (default 0)."""
	_require_write_method(request, '/insert')
	dest = _resolve_op(_first_param(pars, 'path'))
	op_type = _first_param(pars, 'opType')
	if not op_type:
		raise ValueError("missing required 'opType' query parameter")
	input_index = int(_first_param(pars, 'input', '0'))
	parent = dest.parent()
	connectors = dest.inputConnectors
	if input_index >= len(connectors):
		raise ValueError(f"input index {input_index} out of range for '{dest.path}' ({len(connectors)} input connectors)")
	conns = connectors[input_index].connections
	src = conns[0].owner if conns else None
	orig_x, orig_y = dest.nodeX, dest.nodeY
	shift = 200
	for sib in _nodes_in_comp(parent):
		if sib.nodeX >= orig_x:
			sib.nodeX += shift
	name = _first_param(pars, 'name')
	new_node = parent.create(op_type, name) if name else parent.create(op_type)
	new_node.viewer = True
	new_node.nodeX = orig_x
	new_node.nodeY = orig_y
	if src is not None:
		new_node.setInputs([src])
	current_inputs = []
	for conn in dest.inputConnectors:
		c = conn.connections
		current_inputs.append(c[0].owner if c else None)
	current_inputs[input_index] = new_node
	dest.setInputs(current_inputs)
	_ok_json(response, {
		'inserted': _node_summary(new_node),
		'source': src.path if src else None,
		'dest': dest.path,
		'input': input_index,
	})


def _route_reload(request, response, pars, **_):
	reloaded, skipped = op.App.ReloadModules()
	_ok_json(response, {'reloaded': reloaded, 'skipped': skipped})


def _route_health(request, response, pars, webServerDAT, **_):
	node_paths = _first_param(pars, 'nodes')
	stats = []
	if node_paths:
		for p in node_paths.split(','):
			p = p.strip()
			n = op(p)
			if n is not None:
				stats.append({
					'path': n.path,
					'opType': n.opType,
					'cpuCookTime': n.cpuCookTime,
					'gpuCookTime': n.gpuCookTime,
					'totalCooks': n.totalCooks,
					'cookedThisFrame': n.cookedThisFrame,
					'cookedPreviousFrame': n.cookedPreviousFrame,
				})
	_ok_json(response, {
		'cookRate': project.cookRate,
		'realTime': project.realTime,
		'webServerCpuCookTime': webServerDAT.cpuCookTime,
		'webServerTotalCooks': webServerDAT.totalCooks,
		'nodes': stats,
	})


def _route_server_info(request, response, pars, webServerDAT, **_):
	"""Identify the running bridge itself: the Web Server DAT, its Callbacks DAT, and whether
	that DAT is file-synced (edit-the-file-directly) or an embedded snapshot (needs /dat pushes
	to update route code). Generalizes the "find the webserver + callbacks DAT" /run probe that
	otherwise gets rewritten by hand every time this question comes up."""
	cb = webServerDAT.par.callbacks.eval()
	info = {
		'webserver': webServerDAT.path,
		'port': webServerDAT.par.port.eval(),
		'active': webServerDAT.par.active.eval(),
		'callbacksDAT': cb.path if cb else None,
		'callbacksFile': (cb.par.file.eval() if cb is not None and hasattr(cb.par, 'file') else None),
		'callbacksSyncFile': (cb.par.syncfile.eval() if cb is not None and hasattr(cb.par, 'syncfile') else None),
	}
	_ok_json(response, info)


def _route_cookstats(request, response, pars, **_):
	"""Read-only cook-cost snapshot for a subtree, scan-style like /errors (path/family/recursive
	or an explicit paths list) instead of /health's fixed comma-separated 'nodes' list. Intended for
	client-side before/after diffing around a state change (call once, trigger the change, call again,
	diff the two responses) — deliberately does NOT sleep/wait server-side, since this callback runs
	on TD's main thread and a blocking sleep here would freeze the whole UI for its duration."""
	paths_param = _first_param(pars, 'paths') or _first_param(pars, 'path')
	family = _first_param(pars, 'family')
	if paths_param and not family and not _first_param(pars, 'recursive'):
		targets = [_resolve_op(p.strip()) for p in paths_param.split(',') if p.strip()]
	else:
		comp = _resolve_op(paths_param) if paths_param else _get_current_network()
		recursive = _bool_param(pars, 'recursive')
		nodes = comp.findChildren(includeUtility=True) if recursive else _nodes_in_comp(comp)
		if family:
			nodes = [n for n in nodes if n.family == family]
		targets = nodes
	stats = [{
		'path': n.path,
		'opType': n.opType,
		'totalCooks': n.totalCooks,
		'cpuCookTime': n.cpuCookTime,
		'gpuCookTime': n.gpuCookTime,
		'cookedThisFrame': n.cookedThisFrame,
	} for n in targets]
	_ok_json(response, {'sampledAt': time.time(), 'nodes': stats})


def _route_snapshot(request, response, pars, **_):
	target = _resolve_op(_first_param(pars, 'path'))
	if not target.isTOP:
		raise ValueError(f"'{target.path}' is not a TOP (family={target.family})")
	if _bool_param(pars, 'force', True):
		target.cook(force=True)
	filetype = _first_param(pars, 'format', '.png')
	quality = float(_first_param(pars, 'quality', '1.0'))
	data, mime = _snapshot_top(target, filetype, quality)
	response['statusCode'] = 200
	response['statusReason'] = 'OK'
	response['content-type'] = mime
	response['data'] = data


def _route_chop(request, response, pars, **_):
	target = _resolve_op(_first_param(pars, 'path'))
	if not target.isCHOP:
		raise ValueError(f"'{target.path}' is not a CHOP (family={target.family})")
	if _bool_param(pars, 'force', True):
		target.cook(force=True)
	max_samples = int(_first_param(pars, 'samples', '100'))
	_ok_json(response, _chop_data(target, max_samples))


def _route_dat(request, response, pars, **_):
	target = _resolve_op(_first_param(pars, 'path'))
	if not target.isDAT:
		raise ValueError(f"'{target.path}' is not a DAT (family={target.family})")
	if request['method'] in ('POST', 'PUT'):
		if not target.isEditable:
			raise ValueError(f"'{target.path}' is not editable")
		body = request.get('data', '') or ''
		if target.isTable:
			target.csv = body
		else:
			target.text = body
		_ok_text(response, f'updated {target.path} ({len(body)} chars)')
	else:
		_ok_text(response, target.csv if target.isTable else target.text)


def _route_par(request, response, pars, **_):
	target = _resolve_op(_first_param(pars, 'path'))
	par_name = _first_param(pars, 'par')
	if not par_name:
		raise ValueError("missing required 'par' query parameter")
	par = target.par[par_name]
	if par is None:
		raise ValueError(f"no parameter named '{par_name}' on '{target.path}'")
	if request['method'] in ('POST', 'PUT'):
		expr = _first_param(pars, 'expr')
		raw_value = _first_param(pars, 'value')
		if expr is not None:
			par.expr = expr
		elif raw_value is not None:
			par.val = _coerce_par_value(par, raw_value)
		else:
			raise ValueError("must supply 'value' or 'expr' query parameter to set a parameter")
	_ok_json(response, _describe_par(par))


def _route_create(request, response, pars, **_):
	_require_write_method(request, '/create')
	parent_path = _first_param(pars, 'parent')
	parent = _resolve_op(parent_path) if parent_path else _get_current_network()
	if not parent.isCOMP:
		raise ValueError(f"'{parent.path}' is not a COMP, can't create children inside it")
	op_type = _first_param(pars, 'opType')
	if not op_type:
		raise ValueError("missing required 'opType' query parameter")
	inputs = _resolve_inputs(_first_param(pars, 'inputs'))
	name = _first_param(pars, 'name')
	new_node = parent.create(op_type, name) if name else parent.create(op_type)
	new_node.viewer = _bool_param(pars, 'viewer', True)
	x = _first_param(pars, 'x')
	y = _first_param(pars, 'y')
	if x is None and y is None:
		nx, ny = _auto_place(parent, inputs, exclude=new_node)
		new_node.nodeX = nx
		new_node.nodeY = ny
	else:
		if x is not None:
			new_node.nodeX = float(x)
		if y is not None:
			new_node.nodeY = float(y)
	if inputs:
		new_node.setInputs(inputs)
	_ok_json(response, _node_summary(new_node))


def _route_create_from_template(request, response, pars, **_):
	_require_write_method(request, '/create-from-template')
	template_name = _first_param(pars, 'template')
	if not template_name:
		raise ValueError("missing required 'template' query parameter")
	template = _load_template(template_name)
	parent_path = _first_param(pars, 'parent')
	parent = _resolve_op(parent_path) if parent_path else _get_current_network()
	if not parent.isCOMP:
		raise ValueError(f"'{parent.path}' is not a COMP, can't create children inside it")
	x_offset = float(_first_param(pars, 'x', '0'))
	y_offset = float(_first_param(pars, 'y', '0'))
	name_prefix = _first_param(pars, 'namePrefix', '') or ''
	slot_values = _resolve_slots(template, pars)
	name_to_op = instantiate_template(template, parent, x_offset, y_offset, name_prefix, slot_values)
	_ok_json(response, {
		'template': template_name,
		'root': parent.path,
		'created': {name: n.path for name, n in name_to_op.items()},
	})


def _route_wire(request, response, pars, **_):
	_require_write_method(request, '/wire')
	target = _resolve_op(_first_param(pars, 'path'))
	inputs = _resolve_inputs(_first_param(pars, 'inputs'))
	target.setInputs(inputs)
	_ok_json(response, _node_summary(target))


def _route_duplicate(request, response, pars, **_):
	_require_write_method(request, '/duplicate')
	paths_param = _first_param(pars, 'paths') or _first_param(pars, 'path')
	if not paths_param:
		raise ValueError("missing required 'path' or 'paths' query parameter")
	sources = [_resolve_op(p.strip()) for p in paths_param.split(',') if p.strip()]
	parent_path = _first_param(pars, 'parent')
	target_parent = _resolve_op(parent_path) if parent_path else sources[0].parent()
	if not target_parent.isCOMP:
		raise ValueError(f"'{target_parent.path}' is not a COMP, can't create children inside it")
	if len(sources) == 1:
		name = _first_param(pars, 'name')
		copies = [target_parent.copy(sources[0], name=name) if name else target_parent.copy(sources[0])]
	else:
		copies = target_parent.copyOPs(sources)
	for n in copies:
		n.viewer = True
	dx = _first_param(pars, 'dx')
	dy = _first_param(pars, 'dy')
	x = _first_param(pars, 'x')
	y = _first_param(pars, 'y')
	if (dx is not None or dy is not None) and (x is not None or y is not None):
		raise ValueError("specify either absolute 'x'/'y' (single copy only) or relative 'dx'/'dy' (any count), not both")
	if dx is not None or dy is not None:
		ddx = float(dx) if dx is not None else 0.0
		ddy = float(dy) if dy is not None else 0.0
		for n in copies:
			n.nodeX += ddx
			n.nodeY += ddy
	elif x is not None or y is not None:
		if len(copies) != 1:
			raise ValueError("absolute 'x'/'y' positioning only supports duplicating a single 'path' — use 'dx'/'dy' for multiple")
		if x is not None:
			copies[0].nodeX = float(x)
		if y is not None:
			copies[0].nodeY = float(y)
	_ok_json(response, [_node_summary(n) for n in copies])


def _route_comment(request, response, pars, **_):
	_require_write_method(request, '/comment')
	paths_param = _first_param(pars, 'paths') or _first_param(pars, 'path')
	if not paths_param:
		raise ValueError("missing required 'path' or 'paths' query parameter")
	text = _first_param(pars, 'text')
	if text is None:
		raise ValueError("missing required 'text' query parameter (pass an empty string to clear)")
	targets = [_resolve_op(p.strip()) for p in paths_param.split(',') if p.strip()]
	for n in targets:
		n.comment = text
	_ok_json(response, [{'path': n.path, 'comment': n.comment} for n in targets])


# Every one of these is a plain Python attribute on OP ("Common Flags" in TD's own docs) —
# never a Par, so /par can never reach them. Only /run (or this generic /flag route) can.
_KNOWN_OP_FLAGS = frozenset((
	'activeViewer', 'allowCooking', 'bypass', 'cloneImmune', 'current', 'display',
	'expose', 'lock', 'python', 'render', 'selected', 'showCustomOnly', 'showDocked',
	'viewer',
))


def _route_flag(request, response, pars, **_):
	_require_write_method(request, '/flag')
	name = _first_param(pars, 'name')
	if not name:
		raise ValueError(f"missing required 'name' query parameter (one of: {', '.join(sorted(_KNOWN_OP_FLAGS))})")
	if name not in _KNOWN_OP_FLAGS:
		raise ValueError(f"unknown flag '{name}' — must be one of: {', '.join(sorted(_KNOWN_OP_FLAGS))}")
	value = _bool_param(pars, 'value', True)
	paths_param = _first_param(pars, 'paths') or _first_param(pars, 'path')
	family = _first_param(pars, 'family')
	# Disambiguate 'path' as a single explicit target (no family/recursive given) vs. a
	# scan root (family and/or recursive given) — mirrors /errors' path+recursive scan mode.
	if paths_param and not family and not _first_param(pars, 'recursive'):
		targets = [_resolve_op(p.strip()) for p in paths_param.split(',') if p.strip()]
	else:
		comp = _resolve_op(paths_param) if paths_param else _get_current_network()
		recursive = _bool_param(pars, 'recursive')
		nodes = comp.findChildren(includeUtility=True) if recursive else _nodes_in_comp(comp)
		if family:
			nodes = [n for n in nodes if n.family == family]
		targets = nodes
	if not targets:
		raise ValueError(f"no nodes found to set '{name}' on")
	for n in targets:
		setattr(n, name, value)
	_ok_json(response, [{'path': n.path, name: getattr(n, name)} for n in targets])


def _route_bypass(request, response, pars, **_):
	# Backward-compatible alias: /bypass is /flag pinned to name=bypass.
	pars = dict(pars)
	pars['name'] = 'bypass'
	_route_flag(request, response, pars)


def _route_annotate(request, response, pars, **_):
	_require_write_method(request, '/annotate')
	paths_param = _first_param(pars, 'paths')
	if not paths_param:
		raise ValueError("missing required 'paths' query parameter (nodes to enclose)")
	nodes = [_resolve_op(p.strip()) for p in paths_param.split(',') if p.strip()]
	parent_path = _first_param(pars, 'parent')
	parent = _resolve_op(parent_path) if parent_path else nodes[0].parent()
	if not parent.isCOMP:
		raise ValueError(f"'{parent.path}' is not a COMP, can't create children inside it")
	title = _first_param(pars, 'title', '') or ''
	body = _first_param(pars, 'body', '') or ''
	mode = _first_param(pars, 'mode', 'networkbox') or 'networkbox'
	if mode not in ('networkbox', 'annotate', 'comment'):
		raise ValueError(f"invalid mode '{mode}'. Must be 'networkbox', 'annotate', or 'comment'")
	pad = float(_first_param(pars, 'pad', '40'))
	annotation = _create_annotation(parent, nodes, title=title, body=body, mode=mode, pad=pad)
	_ok_json(response, _node_summary(annotation))


def _route_move(request, response, pars, **_):
	_require_write_method(request, '/move')
	paths_param = _first_param(pars, 'paths') or _first_param(pars, 'path')
	if not paths_param:
		raise ValueError("missing required 'path' or 'paths' query parameter")
	targets = [_resolve_op(p.strip()) for p in paths_param.split(',') if p.strip()]
	dx = _first_param(pars, 'dx')
	dy = _first_param(pars, 'dy')
	x = _first_param(pars, 'x')
	y = _first_param(pars, 'y')
	if (dx is not None or dy is not None) and (x is not None or y is not None):
		raise ValueError("specify either absolute 'x'/'y' or relative 'dx'/'dy', not both")
	if dx is not None or dy is not None:
		ddx = float(dx) if dx is not None else 0.0
		ddy = float(dy) if dy is not None else 0.0
		for n in targets:
			n.nodeX += ddx
			n.nodeY += ddy
	else:
		if x is None and y is None:
			raise ValueError("must supply 'x'/'y' (absolute) or 'dx'/'dy' (relative)")
		if len(targets) != 1:
			raise ValueError("absolute 'x'/'y' positioning only supports a single 'path' — use 'paths' with 'dx'/'dy' to shift a group")
		n = targets[0]
		if x is not None:
			n.nodeX = float(x)
		if y is not None:
			n.nodeY = float(y)
	_ok_json(response, [_node_summary(n) for n in targets])


def _route_delete(request, response, pars, **_):
	if request['method'] not in ('POST', 'DELETE'):
		raise MethodNotAllowedError("/delete requires POST or DELETE")
	paths_param = _first_param(pars, 'paths') or _first_param(pars, 'path')
	if not paths_param:
		raise ValueError("missing required 'path' or 'paths' query parameter")
	targets = [_resolve_op(p.strip()) for p in paths_param.split(',') if p.strip()]
	deleted = [n.path for n in targets]
	for n in targets:
		n.destroy()
	_ok_json(response, {'deleted': deleted})


def _route_bounds(request, response, pars, **_):
	paths_param = _first_param(pars, 'paths')
	comp_path = _first_param(pars, 'path')
	if paths_param:
		targets = [_resolve_op(p.strip()) for p in paths_param.split(',') if p.strip()]
	else:
		comp = _resolve_op(comp_path) if comp_path else _get_current_network()
		targets = _nodes_in_comp(comp)
	if not targets:
		raise ValueError("no nodes found to compute bounds for")
	_ok_json(response, _bounds_of(targets))


def _route_errors(request, response, pars, **_):
	paths_param = _first_param(pars, 'paths')
	recursive = _bool_param(pars, 'recursive')
	if paths_param:
		# explicit targets: always return full state (errors AND clean), so a caller
		# checking "did my fix resolve this" gets an explicit confirmation, not silence.
		targets = [_resolve_op(p.strip()) for p in paths_param.split(',') if p.strip()]
		force = _bool_param(pars, 'force', True)
	else:
		comp_path = _first_param(pars, 'path')
		comp = _resolve_op(comp_path) if comp_path else _get_current_network()
		targets = comp.findChildren(includeUtility=True) if recursive else _nodes_in_comp(comp)
		force = _bool_param(pars, 'force', False)
	if force:
		for n in targets:
			n.cook(force=True)
	results = [_op_error_state(n) for n in targets]
	if not paths_param and not _bool_param(pars, 'all'):
		results = [r for r in results if r['errors'] or r['warnings']]
	_ok_json(response, results)


def _route_logs(request, response, pars, **_):
	limit = int(_first_param(pars, 'limit', '50'))
	_ok_json(response, _REQUEST_LOG[-limit:])


def _route_run(request, response, pars, webServerDAT, **_):
	_require_write_method(request, '/run')
	code = request.get('data', '') or ''
	if not code:
		raise ValueError("missing required script body inside POST/PUT data")
	old_stdout, old_stderr = sys.stdout, sys.stderr
	buf = io.StringIO()
	sys.stdout = sys.stderr = buf
	error = None
	try:
		exec(code, {'op': op, 'ops': ops, 'ui': ui, 'project': project, 'me': webServerDAT})
	except Exception:
		error = traceback.format_exc()
	finally:
		sys.stdout, sys.stderr = old_stdout, old_stderr
	result = {'output': buf.getvalue()}
	if error:
		result['error'] = error
	_ok_json(response, result)


def _route_diff(request, response, pars, **_):
	_require_write_method(request, '/diff')
	body = request.get('data', '') or ''
	try:
		payload = json.loads(body)
	except Exception as e:
		raise ValueError(f"body must be JSON: {e}")
	before = payload.get('before')
	after = payload.get('after')
	if before is None or after is None:
		raise ValueError("body must be JSON with both 'before' and 'after' network snapshots (each a /network response)")
	_ok_json_sorted(response, diff_networks(before, after))


# Dispatch table — maps URI → handler function.
_ROUTES = {
	'/network':              _route_network,
	'/network.mmd':          _route_network_mmd,
	'/selected':             _route_selected,
	'/select':               _route_select,
	'/insert':               _route_insert,
	'/reload':               _route_reload,
	'/health':               _route_health,
	'/server-info':          _route_server_info,
	'/cookstats':            _route_cookstats,
	'/snapshot':             _route_snapshot,
	'/chop':                 _route_chop,
	'/dat':                  _route_dat,
	'/par':                  _route_par,
	'/create':               _route_create,
	'/create-from-template': _route_create_from_template,
	'/wire':                 _route_wire,
	'/duplicate':            _route_duplicate,
	'/comment':              _route_comment,
	'/bypass':               _route_bypass,
	'/flag':                 _route_flag,
	'/annotate':             _route_annotate,
	'/move':                 _route_move,
	'/delete':               _route_delete,
	'/bounds':               _route_bounds,
	'/errors':               _route_errors,
	'/logs':                 _route_logs,
	'/run':                  _route_run,
	'/diff':                 _route_diff,
}

_KNOWN_ROUTES = ', '.join(sorted(_ROUTES))


# ---------------------------------------------------------------------------
# Web Server DAT callbacks
# ---------------------------------------------------------------------------

def onHTTPRequest(webServerDAT, request, response):
	callback_start = time.time()
	uri = request['uri']
	pars = request.get('pars', {})

	try:
		handler = _ROUTES.get(uri)
		if handler is None:
			response['statusCode'] = 404
			response['statusReason'] = 'Not Found'
			response['content-type'] = 'text/plain'
			response['data'] = f"unknown route '{uri}'. try {_KNOWN_ROUTES}"
		else:
			handler(request, response, pars, webServerDAT=webServerDAT)
	except MethodNotAllowedError as e:
		response['statusCode'] = 405
		response['statusReason'] = 'Method Not Allowed'
		response['content-type'] = 'text/plain'
		response['data'] = str(e)
	except ValueError as e:
		response['statusCode'] = 400
		response['statusReason'] = 'Bad Request'
		response['content-type'] = 'text/plain'
		response['data'] = str(e)
	except Exception as e:
		response['statusCode'] = 500
		response['statusReason'] = 'Internal Server Error'
		response['content-type'] = 'text/plain'
		response['data'] = str(e)

	callback_elapsed_ms = (time.time() - callback_start) * 1000
	log_entry = {
		'time': time.strftime('%H:%M:%S'),
		'method': request['method'],
		'uri': uri,
		'requestKeys': sorted(request.keys()),
		'dataLen': len(request.get('data') or ''),
		'statusCode': response.get('statusCode'),
		'callbackElapsedMs': round(callback_elapsed_ms, 2),
	}
	_log_request(log_entry)
	print(f"[td_http_api] {log_entry['method']} {uri} -> {log_entry['statusCode']} "
		f"(callback took {log_entry['callbackElapsedMs']}ms, requestKeys={log_entry['requestKeys']}, dataLen={log_entry['dataLen']})")

	return response


def onWebSocketOpen(webServerDAT, client, uri):
	return


def onWebSocketClose(webServerDAT, client):
	return


def onWebSocketReceiveText(webServerDAT, client, data):
	return


def onWebSocketReceiveBinary(webServerDAT, client, data):
	return


def onServerStart(webServerDAT):
	print(f'[td_http_api] server started: {webServerDAT.path}')
	return


def onServerStop(webServerDAT):
	print(f'[td_http_api] server stopped: {webServerDAT.path}')
	return
