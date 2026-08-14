import inspect
import math

import penner

_SHOW     = 'show'   # queue sentinel values
_HIDE     = 'hide'
_EASE_FNS = [name for name, obj in inspect.getmembers(penner, inspect.isfunction) if 'Norm' in name]


class AppStoreToggle:
	"""
	Manages show/hide transitions with optional queue support.
	When Queuetransitions is enabled, a show/hide call issued mid-ramp is held
	until the current transition completes, then fired automatically.

	The transition ramp and all output logic lives in cook(), called every frame
	by execute1 (onFrameEnd). Values are written directly to the const_out
	Constant CHOP via parameter assignment.
	"""

	def __init__(self, ownerComp):
		self.ownerComp = ownerComp
		self.init()

	def init(self):
		self._pendingShow = None   # run() handle while show delay is counting down
		self._pendingHide = None   # run() handle while hide delay is counting down
		self._queued      = None   # _SHOW, _HIDE, or None

		self._showVal     = 0.0    # current lerped value [0, 1]
		self._targetVal   = 0.0    # target: 0 (hidden) or 1 (shown)
		self._duration    = 0.5    # current transition duration in seconds
		self._pulses      = set()  # channel names pulsed this frame

	# ------------------------------------------------------------------
	# Public API
	# ------------------------------------------------------------------

	def Active(self):
		return self._targetVal > 0

	def SetValue(self, newVal):
		self._targetVal = float(newVal)

	def Show(self):
		if self._pendingHide is not None:   # cancel hide delay regardless of queueing
			self._pendingHide.kill()
			self._pendingHide = None
		if self._shouldQueue() and 0 < self._showVal < 1:
			self._queued = _SHOW
			return
		self._queued = None
		self._duration = parent().par.Showduration.eval()
		delayMs = parent().par.Showdelay.eval() * 1000
		def _do_show():
			self._pendingShow = None
			self.SetValue(1)
		self._pendingShow = run(_do_show, delayMilliSeconds=delayMs)
		self.doCallback('show')
		if self._showVal > 0:
			self.doCallback('will_show')

	def Hide(self):
		if self._pendingShow is not None:   # cancel show delay regardless of queueing
			self._pendingShow.kill()
			self._pendingShow = None
		if self._shouldQueue() and 0 < self._showVal < 1:
			self._queued = _HIDE
			return
		self._queued = None
		self._duration = parent().par.Hideduration.eval()
		def _do_hide():
			self._pendingHide = None
			self.SetValue(0)
		self._pendingHide = run(_do_hide, delayMilliSeconds=parent().par.Hidedelay.eval() * 1000)
		self.doCallback('hide')
		if self._showVal < 1:
			self.doCallback('will_hide')

	def OnFrameEnd(self, dt: float) -> None:
		"""Advance the ramp by dt seconds and write all channels to the Constant CHOP.
		Called every frame by execute1 (onFrameEnd)."""
		prev = self._showVal
		self._pulses.clear()

		# Constant-rate linear ramp toward target
		if self._duration > 0:
			step = dt / self._duration
			delta = self._targetVal - self._showVal
			if abs(delta) <= step:
				self._showVal = self._targetVal
			else:
				self._showVal += math.copysign(step, delta)
		else:
			self._showVal = self._targetVal

		val = self._showVal

		# Crossing detection — mirrors old CheckComplete / trigger CHOP pulses
		if prev == 0.0 and val > 0.0:
			self._pulses.add('will_show')
			self.doCallback('will_show')
		if prev < 1.0 and val >= 1.0:
			self._pulses.add('showing')
			self.doCallback('showing')
			self.ownerComp.color = (0, 1, 0)  # green when fully shown
			if self._queued == _HIDE:
				self._queued = None
				self.Hide()
		if prev == 1.0 and val < 1.0:
			self._pulses.add('will_hide')
			self.doCallback('will_hide')
		if prev > 0.0 and val <= 0.0:
			self._pulses.add('hidden')
			self.doCallback('hidden')
			self.ownerComp.color = (0, 0, 0)  # red when fully hidden
			if self._queued == _SHOW:
				self._queued = None
				self.Show()

		# Apply easing to val before writing output channels
		ease_fn = getattr(penner, parent().par.Easingfunc.eval())
		eased = ease_fn(val)

		# Write directly to Constant CHOP channel params
		c = parent().op('const_out')
		c.par.const0value = eased
		c.par.const1value = eased - 1.0 if self._targetVal == 1.0 else 1.0 - eased
		c.par.const2value = 1.0 - eased
		c.par.const3value = 1.0 if eased > 0.0 else 0.0
		c.par.const4value = 1.0 if 'will_show' in self._pulses else 0.0
		c.par.const5value = 1.0 if 'showing'   in self._pulses else 0.0
		c.par.const6value = 1.0 if 'will_hide' in self._pulses else 0.0
		c.par.const7value = 1.0 if 'hidden'    in self._pulses else 0.0

	def doCallback(self, action):
		"""
		Supported callbacks on parent COMP:
		On_show, On_hide, On_will_show, On_showing, On_will_hide, On_hidden
		
		Each callback receives the extension instance (self) as the sole argument,
		allowing the parent to differentiate between multiple AppStoreToggle instances.
		"""
		if not parent().par.Callbacksactive.eval():
			return
		fn = f'On_{action}'
		if hasattr(self.ownerComp.parent(), fn):
			getattr(self.ownerComp.parent(), fn)(self)

	# ------------------------------------------------------------------
	# Private helpers
	# ------------------------------------------------------------------

	def _shouldQueue(self):
		return parent().par.Queuetransitions.eval()

