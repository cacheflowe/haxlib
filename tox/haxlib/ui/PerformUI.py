
class PerformUI:
	"""
	PerformUI 
	"""
	def __init__(self, ownerComp):
		# The component to which this extension is attached
		self.ownerComp = ownerComp
		self.performWindow = self.ownerComp.op('../window1')
		self.AddStoreListeners()

	# ===============================================
	# Perform mode / window helpers
	# ===============================================

	def LaunchOutputWindow(self, performMode=False):
		self.performWindow.par.winopen.pulse()
		ui.performMode = performMode

	def CloseOutputWindow(self):
		self.performWindow.par.winclose.pulse()

	def PerformModeChanged(self, performMode):
		run(f"op('{self.ownerComp.path}').CheckPerformMode({performMode})", delayFrames=10)
	
	def CheckPerformMode(self, performMode):
		isPerformMode = performMode
		# sync appStore and button state if TD ui toggled perform mode
		if (op.AppStore.GetBoolean(op.App.PERFORM_TOGGLE) != isPerformMode):
			op.AppStore.SetBoolean(op.App.PERFORM_TOGGLE, isPerformMode)
			self.ownerComp.op('AppStorePulseButton_close_window1/button1').par.value0 = 1 if isPerformMode else 0

	# ===============================================
	# AppStore listeners
	# ===============================================

	def AddStoreListeners(self):
		# op.AppStore.AddListener(self)
		op.AppStore.AddListener(self, op.App.PERFORM_TOGGLE)
		op.AppStore.AddListener(self, op.App.LAUNCH_WINDOW)
		op.AppStore.AddListener(self, op.App.CLOSE_WINDOW)

	def OnAppStoreValueChanged(self, key, value, type):
		# print(f"[App] *** {key} = {value} (type: {type})")
		return

	def On_perform_toggle(self, key, value, type):
		ui.performMode = value

	def On_launch_window(self, key, value, type):
		# Launch the output window, keeping the current perform mode
		self.LaunchOutputWindow(ui.performMode) if value == 1 else None

	def On_close_window(self, key, value, type):
		self.CloseOutputWindow() if value == 1 else None
