_SHOW = 'show'  # queue sentinel values
_HIDE = 'hide'


class AppStoreToggle:
	"""
	Manages show/hide transitions with optional queue support.
	When Queuetransitions is enabled, a show/hide call issued mid-ramp is held
	until the current transition completes, then fired automatically.
	"""

	def __init__(self, ownerComp):
		self.ownerComp = ownerComp
		self.init()

	def init(self):
		self._pendingShow = None  # run() handle while show delay is counting down
		self._pendingHide = None  # run() handle while hide delay is counting down
		self._queued      = None  # _SHOW, _HIDE, or None

		self.showChop      = op('constant_show')
		self.outChop       = op('out1')
		self.filterChop    = op('filter_linear')
		self.mathInOutChop = op('math_in_out')

		self.callbackWillShow = op('trigger_will_show')
		self.callbackShow     = op('trigger_showing')
		self.callbackWillHide = op('trigger_will_hide')
		self.callbackHide     = op('trigger_hidden')

	# ------------------------------------------------------------------
	# Public API
	# ------------------------------------------------------------------

	def Active(self):
		return self.showChop.par.const0value > 0

	def SetValue(self, newVal):
		self.showChop.par.const0value = newVal

	def Show(self):
		if self._pendingHide is not None:   # cancel hide delay regardless of queueing
			self._pendingHide.kill()
			self._pendingHide = None
		if self._shouldQueue() and 0 < self.outChop['show'] < 1:
			self._queued = _SHOW
			return
		self._queued = None
		self._applyTransition(gain=1, duration=parent().par.Showduration.eval())
		delayMs = parent().par.Showdelay.eval() * 1000
		def _do_show():
			self._pendingShow = None
			self.SetValue(1)
		self._pendingShow = run(_do_show, delayMilliSeconds=delayMs)
		self.doCallback('show')
		if self.outChop['show'] > 0:
			self.doCallback('will_show')

	def Hide(self):
		if self._pendingShow is not None:   # cancel show delay regardless of queueing
			self._pendingShow.kill()
			self._pendingShow = None
		if self._shouldQueue() and 0 < self.outChop['show'] < 1:
			self._queued = _HIDE
			return
		self._queued = None
		self._applyTransition(gain=-1, duration=parent().par.Hideduration.eval())
		def _do_hide():
			self._pendingHide = None
			self.SetValue(0)
		self._pendingHide = run(_do_hide, delayMilliSeconds=parent().par.Hidedelay.eval() * 1000)
		self.doCallback('hide')
		if self.outChop['show'] < 1:
			self.doCallback('will_hide')

	def CheckComplete(self, val, prev):
		if prev == 0 and val > 0:
			self.callbackWillShow.par.triggerpulse.pulse()
			self.doCallback('will_show')
		if prev < 1 and val >= 1:
			self.callbackShow.par.triggerpulse.pulse()
			self.doCallback('showing')
			if self._queued == _HIDE:
				self._queued = None
				self.Hide()
		if prev == 1 and val < 1:
			self.callbackWillHide.par.triggerpulse.pulse()
			self.doCallback('will_hide')
		if prev > 0 and val <= 0:
			self.callbackHide.par.triggerpulse.pulse()
			self.doCallback('hidden')
			if self._queued == _SHOW:
				self._queued = None
				self.Show()

	def doCallback(self, action):
		"""
		Supported callbacks on parent COMP:
		  On_show, On_hide, On_will_show, On_showing, On_will_hide, On_hidden
		"""
		if not parent().par.Callbacksactive.eval():
			return
		fn = f'On_{action}'
		if hasattr(self.ownerComp.parent(), fn):
			getattr(self.ownerComp.parent(), fn)()

	# ------------------------------------------------------------------
	# Private helpers
	# ------------------------------------------------------------------

	def _shouldQueue(self):
		return parent().par.Queuetransitions.eval()

	def _applyTransition(self, gain, duration):
		self.filterChop.par.width        = duration
		self.mathInOutChop.par.preoff    = -1
		self.mathInOutChop.par.gain      = gain
