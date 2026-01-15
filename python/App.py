class App:
	"""
	App Extension Class

	This class is intended to be the top-level extension for the application.
	It is designed to be attached to the main /project component of the project
	and serves as a central point for initializing the application state.

	- This file/extension is loaded when the project starts
	- This file is reloaded when the text is saved
	- This file is externalized to the `python/extensions` directory
	"""

	# Static constants
	# window/perform controls
	LAUNCH_WINDOW = 'launch_window'
	CLOSE_WINDOW = 'close_window'
	PERFORM_TOGGLE = 'perform_toggle'
	
	# modes
	APP_STATE = 'app_state'
	MODE_ATTRACT = 'attract'
	MODE_GAMEPLAY = 'gameplay'
	MODE_GAME_OVER = 'game_over'

	# node paths
	EMPTY_FRAME_TOP = 'empty_frame_top'

	# other props
	AUDIO_VOLUME = 'audio_volume'

	# ===============================================
	# Custom App Behavior
	# ===============================================

	def __init__(self, ownerComp: containerCOMP):
		self.ownerComp: containerCOMP = ownerComp
		print("[App] Initializing...")
		self.AddOpPaths()
		self.AddStoreListeners()
		if op.AppStore.GetBoolean('is_production') == True:
			run(f"op('{self.ownerComp.path}').LaunchOutputWindow(True)", delayFrames=1000)
		print("[App] Initialized!")

	def AddOpPaths(self):
		op.AppStore.SetString(App.EMPTY_FRAME_TOP, op('/project1/constant_frame').path)

	# ===============================================
	# Global Helpers
	# ===============================================

	def CurState(self):
		return op.AppStore.GetString(App.APP_STATE)

	def SetState(self, state):
		op.AppStore.SetString(App.APP_STATE, state)
	
	def AppW(self):
		return op.AppStore.GetFloat('app_w')
	
	def AppH(self):
		return op.AppStore.GetFloat('app_h')

	# ===============================================
	# AppStore listeners
	# ===============================================

	def AddStoreListeners(self):
		# op.AppStore.AddListener(self)
		# op.AppStore.AddListener(self, App.PERFORM_TOGGLE)
		return

	# def OnAppStoreValueChanged(self, key, value, type):
	# 	print(f"[App] *** {key} = {value} (type: {type})")
	# 	return

	# def On_perform_toggle(self, key, value, type):
	# 	ui.performMode = value
