from __future__ import annotations
import os
import td
import config
from typing import ClassVar
from AppStore import AppStore

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
	AUDIO_ANALYSIS_DATA = 'audio_analysis_data'
	SHOW_PIXEL_MAP = 'show_pixel_map'
	BEAT_COUNT = 'beat_count'

	# singleton, set in __init__
	i: ClassVar[App] = None  # type: ignore

	# Singleton access in App, pre-initialized, for use in Bootstrap and other early loading extensions 
	@property
	def AppStore(self) -> AppStore:
		# Singleton access to the AppStore instance safely on init
		# Outside of App.py we can use `AppStore.i`
		return op.AppStore

	# ===============================================
	# Custom App Behavior
	# ===============================================
	
	def __init__(self, ownerComp: containerCOMP):
		self.ownerComp: containerCOMP = ownerComp
		self.RegisterSingletons()
		print("[App] =============================")
		print("[App] Initializing...")
		print("[App] =============================")
		self.Bootstrap()
		self.AddOpPaths()
		self.ResizeExtensionNodes()
		self.AddStoreListeners()
		if self.AppStore.GetBoolean('is_production') == True:
			run(f"op('{self.ownerComp.path}').LaunchOutputWindow(True)", delayFrames=1000)
		self.SetInitialMode()
		print("[App] Initialized!")

	def Bootstrap(self):
		self.AppStore.LoadFile()
		config.LoadEnvFile(os.path.join(project.folder, '.env'))
		self.AppStore.par.Applydefaults.pulse()
		td.reloadModules = config.ReloadModules # make global reload function available for dev use


	def RegisterSingletons(self) -> None:
		App.i = config.register_singleton(self, 'App')
		AppStore.i = config.register_singleton(op.AppStore.ext.AppStore, 'AppStore')  # type: ignore[name-defined]
		# Add future global extensions here: Colors.i = config.register_singleton(op.Colors.ext.Colors, 'Colors')

	def SetInitialMode(self):
		if self.AppStore.GetString(App.APP_STATE, "NONE") != "NONE":
			# Resume previous state in AppStore on startup
			print(f"[App] Resetting current state: {self.CurState()}")
			curState = self.CurState()
			run(f"op('{self.ownerComp.path}').SetState('{curState}')", delayFrames=5)
			return

	def AddOpPaths(self):
		self.AppStore.SetString(App.EMPTY_FRAME_TOP, op('/project1/constant_frame').path)
	
	def ResizeExtensionNodes(self):
		opAppStore = self.ownerComp.op('AppStore')
		opApp = self.ownerComp.op('App')
		if opAppStore is not None:
			opApp.nodeWidth = opAppStore.nodeWidth
			opApp.nodeHeight = opAppStore.nodeHeight

	# ===============================================
	# Global Helpers
	# ===============================================

	def CurState(self):
		return self.AppStore.GetString(App.APP_STATE)

	def SetState(self, state):
		self.AppStore.SetString(App.APP_STATE, state)
	
	def AppW(self):
		return self.AppStore.GetFloat('app_w')
	
	def AppH(self):
		return self.AppStore.GetFloat('app_h')

	# ===============================================
	# AppStore listeners
	# ===============================================

	def AddStoreListeners(self):
		# self.AppStore.AddListener(self)
		# self.AppStore.AddListener(self, App.PERFORM_TOGGLE)
		return

	# def OnAppStoreValueChanged(self, key, value, type):
	# 	print(f"[App] *** {key} = {value} (type: {type})")
	# 	return

	# def On_perform_toggle(self, key, value, type):
	# 	ui.performMode = value
