from __future__ import annotations
from typing import ClassVar

from AppStore import AppStore
from Colors import Colors

import os
import json
import td

import config

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
	MAIN_SECTIONS_LIST = [MODE_ATTRACT, MODE_GAMEPLAY, MODE_GAME_OVER]
	APP_STATE_BUTTONS = 'app_state_buttons'  # replace buttons on www/TD UI

	# node paths
	EMPTY_FRAME_TOP = 'empty_frame_top'

	# other props
	AUDIO_VOLUME = 'audio_volume'
	SFX = 'sfx'
	AUDIO_ANALYSIS_DATA = 'audio_analysis_data'
	BRIGHTNESS = 'brightness'
	SHOW_PIXEL_MAP = 'show_pixel_map'
	BEAT_COUNT = 'beat_count'

	# Timing constants
	LAUNCH_OUTPUT_WINDOW_DELAY_FRAMES = 1000  # ~17s @ 60fps — wait for full project warm-up before going fullscreen
	SET_STATE_DELAY_FRAMES = 5  # short defer so listeners are registered before state resumes

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
			run(f"op('{self.ownerComp.path}').LaunchOutputWindow(True)", delayFrames=App.LAUNCH_OUTPUT_WINDOW_DELAY_FRAMES)
		self.SetInitialMode()
		run(lambda: self.BuildAppStateForUI(), delayMilliSeconds=1000)
		print("[App] Initialized!")

	def Bootstrap(self):
		# Load order: defaults (lowest) → persisted file → .env → shell env → hard-coded (highest)
		# Suppress listener notifications until all layers are loaded
		self.AppStore.SuppressNotifications()
		print("[App] Bootstrap: 1/4 SetDefaults(force=True)")
		self.AppStore.SetDefaults(force=True)
		print("[App] Bootstrap: 2/4 LoadFile()")
		self.AppStore.LoadFile()
		print("[App] Bootstrap: 3/4 LoadEnvFile()")
		config.LoadEnvFile(os.path.join(project.folder, '.env'))
		print("[App] Bootstrap: 4/4 LoadSystemEnvVars()")
		self.LoadSystemEnvVars()
		self.AppStore.ResumeNotifications()
		# set reload modules on global td for easy access from textport:
		# - op.App.ReloadModules()
		# - td.reloadModules()  # alias for convenience
		td.reloadModules = config.ReloadModules

	def ReloadModules(self):
		return config.ReloadModules()

	def LoadSystemEnvVars(self):
		"""Load OS-level environment variables that may have been set by the launching script
		(e.g. scripts/run-td-app-plus-env-var.cmd). Each call falls back to the default value
		if the OS env var is not set. Add project-specific keys here.
		"""
		config.LoadSystemEnvironmentVar('sys_env_var', 'Default Value')

	def VerifyBootstrap(self):
		"""Diagnostic — prints currently loaded values. Call manually from the textport
		(`op('/project1').VerifyBootstrap()`) when investigating bootstrap precedence."""
		print("[App] ---- Bootstrap Verification ----")
		print(f"[App]   is_production = {self.AppStore.GetBoolean('is_production')}")
		print(f"[App]   app_w = {self.AppStore.GetFloat('app_w')}")
		print(f"[App]   app_h = {self.AppStore.GetFloat('app_h')}")
		print(f"[App]   Total keys in store: {self.AppStore.GetStoreDat().numRows}")
		print("[App] ---- End Verification ----")

	def RegisterSingletons(self) -> None:
		App.i = config.register_singleton(self, 'App')
		AppStore.i = config.register_singleton(op.AppStore.ext.AppStore, 'AppStore')  # type: ignore[name-defined]
		Colors.i = config.register_singleton(op.Colors.ext.Colors, 'Colors')  # type: ignore[name-defined]

	def SetInitialMode(self):
		curState = self.CurState()
		if curState and curState != "NONE":
			print(f"[App] Resuming state: {curState}")
			run(f"args[0].SetState(args[1])", self, curState, delayFrames=App.SET_STATE_DELAY_FRAMES)
			return

	def BuildAppStateForUI(self):
		self.AppStore.SetStringFromObj(App.APP_STATE_BUTTONS, App.MAIN_SECTIONS_LIST, broadcast=True)

	def AddOpPaths(self):
		self.AppStore.SetString(App.EMPTY_FRAME_TOP, op('/project1/constant_frame').path)
	
	def ResizeExtensionNodes(self):
		opAppStore = self.ownerComp.op('AppStore')
		opApp = self.ownerComp.op('App')
		if opAppStore is None or opApp is None:
			return
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

	def PlaySFX(self, sfxName):
		self.AppStore.SetString(App.SFX, sfxName)

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
