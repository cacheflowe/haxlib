# chop_elastic_float.py
# Script CHOP — Hooke's-law elastic follower for one or more channels.
#
# Usage as a Script CHOP:
#   - Wire any CHOP into input 0 as the target (all channels are followed).
#   - Output channels mirror input names: <name> and <name>_speed per channel.
#   - Tune feel via the Preset dropdown or Custom sliders on the Elastic page.
#
# Usage as a standalone class (extension or plain Python):
#   elastic = ElasticFloat(value=0.0, fric=0.85, accel=0.12)
#   elastic.set_target(1.0)
#   current = elastic.update(dt=1/60, snap=0.001)  # dt = 1 / your_fps

import math

# Reference frame duration for dt normalisation (60 fps baseline).
# All presets are tuned at this rate; physics scales automatically above/below.
_REF_DT: float = 1.0 / 60.0


class ElasticFloat:
	"""Hooke's-law elastic follower for a single float value.

	Args:
		value:  Starting value.
		fric:   Friction [0-1]. Lower = more damping (slower stop).
		accel:  Acceleration [0-1]. Lower = slower response.
	"""

	def __init__(self, value: float = 0.0, fric: float = 0.85, accel: float = 0.12) -> None:
		self.val: float = value
		self.fric: float = max(0.0, min(1.0, fric))
		self.accel: float = max(0.0, min(1.0, accel))
		self.targetVal: float = value
		self.speed: float = 0.0

	# ------------------------------------------------------------------
	# Getters
	# ------------------------------------------------------------------

	def value(self) -> float:
		return self.val

	def target(self) -> float:
		return self.targetVal

	# ------------------------------------------------------------------
	# Setters (fluent — return self for chaining)
	# ------------------------------------------------------------------

	def set_current(self, value: float) -> 'ElasticFloat':
		self.val = value
		return self

	def set_target(self, target: float) -> 'ElasticFloat':
		self.targetVal = target
		return self

	def set_friction(self, fric: float) -> 'ElasticFloat':
		self.fric = max(0.0, min(1.0, fric))
		return self

	def set_accel(self, accel: float) -> 'ElasticFloat':
		self.accel = max(0.0, min(1.0, accel))
		return self

	# ------------------------------------------------------------------
	# Core
	# ------------------------------------------------------------------

	def update(self, dt: float = _REF_DT, snap: float = 0.0) -> float:
		"""Advance one step toward the target. Call once per frame.

		Args:
			dt:   Frame duration in seconds. Scales physics so the feel is
			      consistent at any frame rate (reference: 60 fps = 1/60 s).
			snap: Distance+speed threshold below which val snaps exactly to
			      targetVal and momentum is zeroed. Eliminates micro-jitter.
		"""
		if not math.isfinite(self.targetVal):
			return self.val

		# Normalise to the 60 fps reference so presets feel the same at any FPS.
		# Cap at 4x to avoid huge steps after lag spikes or on the first frame.
		t = max(0.0, min(dt / _REF_DT, 4.0))
		fric_t  = self.fric ** t   # exponential decay scales correctly with time
		accel_t = self.accel * t   # linear force scales with time elapsed

		self.speed = ((self.targetVal - self.val) * accel_t + self.speed) * fric_t
		self.val  += self.speed

		# Blow-up guard: snap to target and zero momentum if physics diverges
		if not math.isfinite(self.val) or not math.isfinite(self.speed):
			self.val   = self.targetVal
			self.speed = 0.0
		# Snap threshold: stop micro-jitter once close enough and nearly still
		elif snap > 0.0 and abs(self.targetVal - self.val) < snap and abs(self.speed) < snap:
			self.val   = self.targetVal
			self.speed = 0.0

		return self.val


# ---------------------------------------------------------------------------
# Script CHOP callbacks
# ---------------------------------------------------------------------------

_elastics: list[ElasticFloat] = []

# (name, label, fric, accel)
_PRESETS: list[tuple[str, str, float, float]] = [
	('custom',   'Custom',   0.80, 0.20),
	('smooth',   'Smooth',   0.85, 0.12),
	('snappy',   'Snappy',   0.75, 0.35),
	('elastic',  'Elastic',  0.92, 0.15),
	('bouncy',   'Bouncy',   0.96, 0.08),
	('heavy',    'Heavy',    0.80, 0.04),
]

_PRESET_MAP: dict[str, tuple[float, float]] = {
	name: (fric, accel) for name, _, fric, accel in _PRESETS
}


def _ensure_channels(n: int) -> None:
	"""Grow the _elastics pool to at least n instances."""
	while len(_elastics) < n:
		_elastics.append(ElasticFloat())


def onSetupParameters(scriptOp: scriptCHOP):
	page = scriptOp.appendCustomPage('Elastic')

	preset = page.appendMenu('Preset', label='Preset')[0]
	preset.menuNames  = [p[0] for p in _PRESETS]
	preset.menuLabels = [p[1] for p in _PRESETS]
	preset.default    = 'smooth'
	preset.val        = 'smooth'

	fric = page.appendFloat('Friction', label='Friction')[0]
	fric.default = 0.85
	fric.val     = 0.85

	accel = page.appendFloat('Accel', label='Acceleration')[0]
	accel.default = 0.12
	accel.val     = 0.12

	snap = page.appendFloat('Snap', label='Snap Threshold')[0]
	snap.default = 0.001
	snap.val     = 0.001

	# Warn if multiple inputs have colliding channel names
	if scriptOp.inputs and len(scriptOp.inputs) > 1:
		all_names = []
		for inp_idx, inp in enumerate(scriptOp.inputs):
			for ch_idx in range(inp.numChans):
				all_names.append((inp_idx, inp[ch_idx].name))
		
		seen = {}
		for inp_idx, ch_name in all_names:
			if ch_name not in seen:
				seen[ch_name] = []
			seen[ch_name].append(inp_idx)
		
		collisions = {name: inputs for name, inputs in seen.items() if len(inputs) > 1}
		if collisions:
			msg = ', '.join([f'"{name}"({",".join(map(str, inputs))})' for name, inputs in collisions.items()])
			print(f'Warning: Channel name collisions across inputs: {msg}. Use unique names per input.')
	return


def onCook(scriptOp: scriptCHOP):
	preset_name = scriptOp.par.Preset.eval()

	if preset_name == 'custom':
		fric  = scriptOp.par.Friction.eval()
		accel = scriptOp.par.Accel.eval()
	else:
		fric, accel = _PRESET_MAP[preset_name]
		# Mirror values into sliders so the user can see the active settings
		scriptOp.par.Friction.val = fric
		scriptOp.par.Accel.val    = accel

	snap = scriptOp.par['Snap'].eval() if scriptOp.par['Snap'] is not None else 0.001
	dt   = absTime.stepSeconds

	# Collect all channels from all inputs: list of (input_idx, ch_idx, ch_name)
	channels = []
	if scriptOp.inputs:
		try:
			for inp_idx, inp in enumerate(scriptOp.inputs):
				for ch_idx in range(inp.numChans):
					ch_name = inp[ch_idx].name
					channels.append((inp_idx, ch_idx, ch_name))
		except (TypeError, AttributeError):
			channels = [(0, 0, 'val')]
	else:
		channels = [(0, 0, 'val')]

	n_channels = len(channels)
	_ensure_channels(n_channels)

	# Advance all elastics and collect results
	scriptOp.clear()
	vals = []
	for i, (inp_idx, ch_idx, ch_name) in enumerate(channels):
		e = _elastics[i]
		e.set_friction(fric).set_accel(accel)
		if scriptOp.inputs:
			try:
				e.set_target(scriptOp.inputs[inp_idx][ch_idx][0])
			except (TypeError, IndexError, AttributeError):
				pass
		vals.append(e.update(dt=dt, snap=snap))

	# Output: all vals, then all speeds (grouped by channel across all inputs)
	for i, (_, _, ch_name) in enumerate(channels):
		scriptOp.appendChan(ch_name)[0] = vals[i]
	for i, (_, _, ch_name) in enumerate(channels):
		scriptOp.appendChan(ch_name + '_speed')[0] = _elastics[i].speed
	return


def onGetCookLevel(scriptOp: scriptCHOP) -> CookLevel:
	return CookLevel.AUTOMATIC

