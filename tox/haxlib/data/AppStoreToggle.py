class AppStoreToggle:
	"""
	AppStoreToggle description
	"""
	def __init__(self, ownerComp):
		# The component to which this extension is attached
		self.ownerComp = ownerComp
		self.init()

	def init(self):
		# get ops
		self.showChop = op('constant_show')
		self.outChop = op('out1')
		self.filterChop = op('filter_linear')
		self.mathInOutChop = op('math_in_out') # go from -1 -> 1 for in_out animations
		self.callbackWillShow = op('trigger_will_show')
		self.callbackShow = op('trigger_showing')
		self.callbackWillHide = op('trigger_will_hide')
		self.callbackHide = op('trigger_hidden')
		return

	def Active(self):
		return self.showChop.par.const0value > 0

	def SetValue(self, newVal):
		# if self.showChop.par.const0value == 1:
		# 	return
		self.showChop.par.const0value = newVal

	def Show(self):
		delayMs = parent().par.Showdelay.eval() * 1000
		run(lambda: self.SetValue(1), delayMilliSeconds=delayMs)
		self.filterChop.par.width = parent().par.Showduration.eval()
		self.mathInOutChop.par.preoff = -1
		self.mathInOutChop.par.gain = 1
		self.doCallback('show')
		if self.outChop['show'] > 0:
			self.doCallback('will_show')
		return

	def Hide(self):
		delayMs = parent().par.Hidedelay.eval() * 1000
		run(lambda: self.SetValue(0), delayMilliSeconds=delayMs)
		self.filterChop.par.width = parent().par.Hideduration.eval()
		self.mathInOutChop.par.preoff = -1
		self.mathInOutChop.par.gain = -1
		self.doCallback('hide')
		if self.outChop['show'] < 1:
			self.doCallback('will_hide')
		return
	
	def CheckComplete(self, val, prev):
		if prev == 0 and val > 0:
			self.callbackWillShow.par.triggerpulse.pulse()
			self.doCallback('will_show')
		if prev < 1 and val >= 1:
			self.callbackShow.par.triggerpulse.pulse()
			self.doCallback('showing')
		if prev == 1 and val < 1:
			self.callbackWillHide.par.triggerpulse.pulse()
			self.doCallback('will_hide')
		if prev > 0 and val <= 0:
			self.callbackHide.par.triggerpulse.pulse()
			self.doCallback('hidden')
		return

	def doCallback(self, action):
		"""
		def On_show(self):
		def On_hide(self):
		def On_will_show(self):
		def On_showing(self):
		def On_will_hide(self):
		def On_hidden(self):
		"""
		if parent().par.Callbacksactive.eval() == 0:
			return
		# call dynamic functions
		fn = f'On_{action}'
		if hasattr(self.ownerComp.parent(), fn):
			getattr(self.ownerComp.parent(), fn)()
		# else:
		# 	print(f"[VisualToggle] No callback defined for {action}")
		return