from __future__ import annotations
from typing import Any, ClassVar, Dict, List, Optional

import json
import os
import threading
import time
import uuid
import tdu # Import tdu for Dependency
from subprocess import PIPE, STDOUT, Popen

class AppStore:
	"""
	Global state management extension for TouchDesigner.

	Provides a centralized key-value store with type-aware getters/setters,
	WebSocket synchronization, and Python callback listeners.
	"""

	# singleton, set in App.py
	# AppStore.i is set later by App.RegisterSingletons() → config.register_singleton().
	# That bridges this instance into sys.modules['AppStore'].AppStore.i so that
	# `from AppStore import AppStore` from any other extension/DAT sees it.
	i: ClassVar[AppStore] = None  # type: ignore  

	# Value type constants
	TYPE_NUMBER = 'number'
	TYPE_STRING = 'string'
	TYPE_BOOLEAN = 'boolean'

	DISCONNECT_BANNER = "=" * 60

	# Timing constants
	SAVE_FILE_STARTUP_GUARD_SECONDS = 5  # skip SaveFile() during the first N seconds after launch
	STARTUP_CONNECTION_CHECK_DELAY_MS = 2000  # grace period before logging startup disconnect

	def __init__(self, ownerComp: baseCOMP) -> None:
		self.ownerComp: baseCOMP = ownerComp
		self._suppressNotify: bool = False
		self._pendingKeys: Dict[str, Optional[str]] = {}  # key → valueType, flushed at frame end
		self._disconnectedFallbacks: Dict[str, int] = {}  # key → count of fallback writes during current outage
		self.initListeners()
		self.initStore()
		self.initDependencies() # Initialize granular dependencies
		self.initWebSocket()

	def initListeners(self) -> None:
		self.listeners: List[Any] = []
		self.listenersByKey: Dict[str, List[Any]] = {}

	def initStore(self) -> None:
		"""Initialize internal operator references."""
		self.storeTable: tableDAT = self.ownerComp.op('table_store_dictionary')
		self.numericTable: dattoCHOP = self.ownerComp.op('datto_store_numbers')
		self.fileInTable: tableDAT = self.ownerComp.op('filein_backup')
		self.defaultsTable: tableDAT = self.ownerComp.op('in_default_values')

	def initDependencies(self) -> None:
		"""Initialize granular dependency objects from existing table data."""
		self.dependencies: Dict[str, tdu.Dependency] = {}
		self.SyncFromTable()

	def SyncFromTable(self) -> None:
		"""Update dependency objects from the current table state."""
		# We iterate the table to ensure existing data is reactive
		if self.storeTable.numRows > 0:
			for row in self.storeTable.rows():
				key = row[0].val
				val = row[1].val
				if key not in self.dependencies:
					self.dependencies[key] = tdu.Dependency(val)
				else:
					self.dependencies[key].val = val

	def getSenderId(self) -> str:
		"""Get the sender ID from component parameters."""
		return self.ownerComp.par.Senderid.eval()

	###################################################
	# Node Reference Helpers
	###################################################

	def GetStoreDat(self) -> 'DAT':
		"""Get the store table DAT operator."""
		return self.storeTable

	def GetStoreChop(self) -> 'CHOP':
		"""Get the numeric store CHOP operator."""
		return self.numericTable

	###################################################
	# Getters
	###################################################

	def HasValue(self, key: str) -> bool:
		"""Check if a key exists in the store (checking dependency cache first)."""
		return key in self.dependencies

	def GetFloat(self, key: str, default: float = 0.0) -> float:
		"""Get a numeric value from the store."""
		if key in self.dependencies:
			try:
				return float(self.dependencies[key].val)
			except ValueError:
				pass
		return default

	def GetString(self, key: str, default: str = '') -> str:
		"""
		Get a string value from the store.
		Reading .val from the dependency object ensures only this specific key's
		updates will trigger a cook in the calling operator.
		"""
		if key in self.dependencies:
			return str(self.dependencies[key].val)
		return default

	def GetBoolean(self, key: str, default: bool = False) -> bool:
		"""Get a boolean value from the store.

		Accepts 'true', '1', and '1.0' (case-insensitive) as True — matches TD's
		convention that 0/1 is interchangeable with False/True. Anything else is False.
		"""
		if key in self.dependencies:
			val = str(self.dependencies[key].val).strip().lower()
			return val in ('true', '1', '1.0')
		return default

	###################################################
	# Setters
	###################################################

	def SetValue(self, key: str, value: Any, valueType: Optional[str] = None, sender: Optional[str] = None, broadcast: bool = False) -> None:
		"""Set a value in the store.

		If broadcast=True and the WebSocket is connected, send over the wire and
		wait for the echo to update local state (server-as-truth pattern).
		If broadcast=True but disconnected, fall back to a local update so the
		app keeps functioning offline.
		"""
		if broadcast and self.IsConnected():
			self.broadcastValue(key, value, valueType)
			return

		if broadcast:
			# Disconnected — track fallback for the next connection-restore summary
			self._disconnectedFallbacks[key] = self._disconnectedFallbacks.get(key, 0) + 1

		# Local update (either broadcast=False, or disconnected fallback)
		isNew = key not in self.dependencies
		oldValue = None if isNew else self.dependencies[key].val
		changed = isNew or str(oldValue) != str(value)

		# Update granular dependency (triggers cooks only for listeners of this key)
		if isNew:
			self.dependencies[key] = tdu.Dependency(value)
		else:
			self.dependencies[key].val = value

		# Update Table (triggers cooks for anyone watching the whole table)
		eventId = self.newEventId()
		if self.storeTable.row(key) is not None:
			self.storeTable[key, 1] = value
			self.storeTable[key, 2] = valueType
			self.storeTable[key, 3] = sender or ''
			self.storeTable[key, 4] = eventId
		else:
			self.storeTable.appendRow(
				[key, value, valueType, sender, eventId])

		if changed and not self._suppressNotify:
			self._pendingKeys[key] = valueType

	def SetFloat(self, key: str, value: float, broadcast: bool = False) -> None:
		"""Set a numeric value in the store."""
		self.SetValue(key, value, self.TYPE_NUMBER, self.getSenderId(), broadcast)

	def SetString(self, key: str, value: str, broadcast: bool = False) -> None:
		"""Set a string value in the store."""
		self.SetValue(key, value, self.TYPE_STRING, self.getSenderId(), broadcast)

	def SetStringFromObj(self, key: str, value: Any, broadcast: bool = False) -> None:
		"""Convert an object or array to a JSON string value in the store."""
		self.SetString(key, json.dumps(value), broadcast)

	def SetBoolean(self, key: str, value: bool, broadcast: bool = False) -> None:
		"""Set a boolean value in the store."""
		self.SetValue(key, value, self.TYPE_BOOLEAN, self.getSenderId(), broadcast)

	def SetFromString(self, key: str, rawValue: Any, broadcast: bool = False) -> None:
		"""Infer type from a raw string and store.

		For sources that don't carry type info (.env files, system env vars, etc.).
		Recognizes 'true'/'false' (case-insensitive) as bool. Parses numerics with
		float() — handles negatives, decimals, scientific notation. Preserves
		leading-zero strings like '0123' as strings (likely IDs/codes, not numbers).
		Logs when an existing key is overwritten.
		"""
		if rawValue is None:
			return
		existed = self.HasValue(key)
		s = str(rawValue).strip()
		low = s.lower()
		if low in ('true', 'false'):
			self.SetBoolean(key, low == 'true', broadcast)
		else:
			isLeadingZero = len(s) > 1 and s[0] == '0' and s[1] not in ('.', 'e', 'E')
			parsedFloat = None
			if not isLeadingZero:
				try:
					parsedFloat = float(s)
				except ValueError:
					pass
			if parsedFloat is not None:
				self.SetFloat(key, parsedFloat, broadcast)
			else:
				self.SetString(key, s, broadcast)
		if existed:
			print(f"[AppStore]   (overwriting existing key: {key})")

	def broadcastValue(self, key: str, value: Any, valueType: Optional[str]) -> None:
		"""Broadcast a value change over WebSocket."""
		jsonOut = {
			'store': True,
			'key': key,
			'value': value,
			'type': valueType
		}
		senderId = self.getSenderId()
		if senderId:
			jsonOut['sender'] = senderId
		self.ownerComp.op('websocket1').sendText(json.dumps(jsonOut))

	###################################################
	# Event Listeners
	###################################################

	def AddListener(self, listener: Any, key: Optional[str] = None) -> None:
		"""
		Add a listener for store value changes.

		Args:
				listener: Object with OnAppStoreValueChanged method or On_{key} method
				key: Optional specific key to listen for. If None, listens to all changes.
		"""
		if key is None:
			if listener not in self.listeners:
				self.listeners.append(listener)
		elif hasattr(listener, f'On_{key}'):
			keyListeners = self.listenersByKey.setdefault(key, [])
			if listener not in keyListeners:
				keyListeners.append(listener)
		else:
			print(f"[AppStore] Listener missing required 'On_{key}' method: {listener}")

		self.cleanupDefunctListeners()

	def RemoveListener(self, listener: Any) -> None:
		"""Remove a listener from all subscriptions."""
		removed = False
		if listener in self.listeners:
			self.listeners.remove(listener)
			removed = True
		for key, listeners in self.listenersByKey.items():
			if listener in listeners:
				listeners.remove(listener)
				removed = True
		if not removed:
			print(
				f"[AppStore] RemoveListener() - Listener not found: {listener}")

	def NotifyListeners(self, key: str, value: Any, valueType: Optional[str]) -> None:
		"""Notify all relevant listeners of a value change."""
		needsCleanup = False
		for listener in self.listeners:
			try:
				if hasattr(listener, 'OnAppStoreValueChanged'):
					listener.OnAppStoreValueChanged(key, value, valueType)
				else:
					print(f"[AppStore] Listener {listener} missing OnAppStoreValueChanged method")
			except Exception as e:
				print(f"[AppStore] Listener error (will clean up): {e}")
				needsCleanup = True

		for listener in self.listenersByKey.get(key, []):
			callbackFn = f'On_{key}'
			try:
				if hasattr(listener, callbackFn):
					getattr(listener, callbackFn)(key, value, valueType)
				else:
					print(f"[AppStore] Listener {listener} missing {callbackFn} method for key: {key}")
			except Exception as e:
				print(f"[AppStore] Listener error for key '{key}' (will clean up): {e}")
				needsCleanup = True

		if needsCleanup:
			self.cleanupDefunctListeners()

	def SuppressNotifications(self) -> None:
		"""Pause end-of-frame listener notifications. Pair with ResumeNotifications().
		Use for bulk loads (Bootstrap) where you don't want listeners reacting per-key."""
		self._suppressNotify = True

	def ResumeNotifications(self) -> None:
		"""Resume end-of-frame listener notifications."""
		self._suppressNotify = False

	def FlushNotifications(self) -> None:
		"""Flush pending notifications at end of frame. Called by Execute DAT."""
		if not self._pendingKeys:
			return
		keys = dict(self._pendingKeys)
		self._pendingKeys.clear()
		for key, valueType in keys.items():
			value = self.dependencies[key].val if key in self.dependencies else None
			self.NotifyListeners(key, value, valueType)

	def cleanupDefunctListeners(self) -> None:
		"""Remove old instances of listeners, keeping only the newest instance per ownerComp."""
		delCount = 0
		ownerCompToListener: Dict[Any, Any] = {}

		for listener in self.listeners:
			if hasattr(listener, 'ownerComp'):
				ownerCompToListener[listener.ownerComp] = listener

		for i in range(len(self.listeners) - 1, -1, -1):
			listener = self.listeners[i]
			if hasattr(listener, 'ownerComp'):
				if ownerCompToListener[listener.ownerComp] is not listener:
					del self.listeners[i]
					delCount += 1
					print(
						f"[AppStore] Removed old listener instance: {listener}")

		for key in list(self.listenersByKey.keys()):
			listeners = self.listenersByKey[key]
			ownerCompToListener = {}

			for listener in listeners:
				if hasattr(listener, 'ownerComp'):
					ownerCompToListener[listener.ownerComp] = listener

			for i in range(len(listeners) - 1, -1, -1):
				listener = listeners[i]
				if hasattr(listener, 'ownerComp'):
					if ownerCompToListener[listener.ownerComp] is not listener:
						del listeners[i]
						delCount += 1
						print(
							f"[AppStore] Removed old listener instance for key '{key}': {listener}")

			if not listeners:
				del self.listenersByKey[key]

		if delCount > 0:
			print(f"[AppStore] Cleaned up {delCount} defunct listeners")

	###################################################
	# Utility
	###################################################

	def ClearData(self) -> None:
		"""Clear all data from the store and re-apply defaults.

		Queues notifications for cleared keys with value=None so listeners can
		react to removals. Defaults are then re-applied via SetValue, which
		queues additional notifications for any keys present in the defaults table.
		"""
		if not self._suppressNotify:
			for key in list(self.dependencies.keys()):
				self._pendingKeys[key] = None
		self.storeTable.clear()
		self.dependencies.clear()
		self.SetDefaults()
		self.SaveFile()

	def RemoveValue(self, key: str, broadcast: bool = False) -> None:
		"""Remove a value from the store."""
		if key in self.dependencies:
			del self.dependencies[key]

		if self.storeTable.row(key) is not None:
			valueType = self.storeTable[key, 2].val
			self.storeTable.deleteRow(key)
			if broadcast:
				self.broadcastValue(key, None, valueType)

	def newEventId(self) -> str:
		"""Generate a unique event ID."""
		return f"{time.time()}-{uuid.uuid4()}"

	###################################################
	# WebSocket Connection
	###################################################

	def initWebSocket(self) -> None:
		"""Initialize WebSocket connection state."""
		self._startupConnectionLogged: bool = False
		self.setIsConnected(False)
		self.setColor(1, 1, 0)
		self.CheckSocketReconnect()
		# Grace period for the websocket to connect. If still disconnected after this,
		# log the disconnect banner so startup-with-no-server is visible.
		run("args[0]._startupConnectionCheck()", self, delayMilliSeconds=self.STARTUP_CONNECTION_CHECK_DELAY_MS)

	def _startupConnectionCheck(self) -> None:
		"""Fires once, 2s after init, to log if we started up disconnected."""
		if self._startupConnectionLogged:
			return
		self._startupConnectionLogged = True
		if not self.IsConnected():
			self._logConnectionLost()

	def StartWebServer(self) -> None:
		"""Start the web server if not already connected."""
		if not self.IsConnected():
			print('[AppStore] Starting web server shell script...')
			thread = threading.Thread(target=self.startWebServerThread)
			thread.start()
		else:
			print('[AppStore] Web server already running, skipping shell script')

	def startWebServerThread(self) -> None:
		"""Background thread to run the web server process."""
		p = Popen(
			['web-server-start.cmd'],
			cwd='scripts',
			stdout=PIPE,
			stderr=STDOUT,
			shell=True,
			text=True,
			bufsize=1
		)
		for line in p.stdout:
			print(line, end='')
		p.stdout.close()
		p.wait()

	def OpenWebBrowser(self) -> None:
		"""Open the web browser to the app URL."""
		print('[AppStore] OpenWebBrowser() does nothing right now')

	def setIsConnected(self, state: bool) -> None:
		"""Set the WebSocket connection state."""
		self.ownerComp.op('constant_active').par.value0 = 1 if state else 0

	def IsConnected(self) -> bool:
		"""Check if WebSocket is connected."""
		return self.ownerComp.op('constant_active').par.value0 == 1

	def CheckSocketReconnect(self) -> None:
		"""Attempt to reconnect the WebSocket if disconnected."""
		if not self.IsConnected():
			websocket = self.ownerComp.op('websocket1')
			websocket.par.active = 1
			websocket.par.reset.pulse()

	def SocketConnected(self, websocketDat: websocketDAT) -> None:
		"""Handle WebSocket connection event."""
		if self.IsConnected():
			return  # ignore duplicate state event
		self.setIsConnected(True)
		self.setColor(0, 1, 0)
		self._logConnectionRestored()
		self._disconnectedFallbacks.clear()
		self._startupConnectionLogged = True  # suppress deferred startup check

	def SocketDisconnected(self, websocketDat: websocketDAT) -> None:
		"""Handle WebSocket disconnection event."""
		if not self.IsConnected():
			return  # ignore duplicate state event
		self.setIsConnected(False)
		self.setColor(1, 1, 0)
		self._logConnectionLost()
		self._startupConnectionLogged = True  # suppress deferred startup check

	def _logConnectionLost(self) -> None:
		print(self.DISCONNECT_BANNER)
		print("[AppStore] WebSocket DISCONNECTED")
		print("           broadcast=True writes will fall back to local updates")
		print(self.DISCONNECT_BANNER)

	def _logConnectionRestored(self) -> None:
		print(self.DISCONNECT_BANNER)
		print("[AppStore] WebSocket RECONNECTED")
		if self._disconnectedFallbacks:
			total = sum(self._disconnectedFallbacks.values())
			distinct = len(self._disconnectedFallbacks)
			print(f"           {total} broadcast write(s) across {distinct} key(s) handled locally during outage:")
			for k, count in self._disconnectedFallbacks.items():
				print(f"             - {k}: {count}x")
		else:
			print("           no broadcast writes attempted during outage")
		print(self.DISCONNECT_BANNER)

	def MessageReceived(self, dat: tableDAT, rowIndex: int, message: str) -> None:
		"""Handle incoming WebSocket message."""
		try:
			data = json.loads(message)
		except (json.JSONDecodeError, TypeError) as e:
			preview = (message[:120] + '…') if isinstance(message, str) and len(message) > 120 else message
			print(f"[AppStore] Ignoring malformed WebSocket message: {e} | payload: {preview!r}")
			return

		if data.get('store') == True:
			try:
				key = data['key']
				value = data['value']
				valueType = data['type']
			except KeyError as e:
				print(f"[AppStore] Store message missing required field {e}: {data!r}")
				return
			sender = data.get('sender', '')
			if key == 'persistent_state':
				self._handlePersistentState(value)
			else:
				self.SetValue(key, value, valueType, sender, False)
		else:
			print('[AppStore] Generic json message received')

	def _handlePersistentState(self, stateData: Any) -> None:
		"""Load full persisted state from the server into the store.

		Only applies if the Loadserverstate parameter is enabled.
		stateData is a dict of key -> {key, value, type, sender, ...}.
		"""
		if not self.ownerComp.par.Loadserverstate.eval():
			print('[AppStore] Received persistent_state but Loadserverstate is disabled, ignoring')
			return
		if not isinstance(stateData, dict):
			print(f'[AppStore] persistent_state value is not a dict, ignoring')
			return
		print(f'[AppStore] Loading persistent_state from server ({len(stateData)} keys)')
		for key, entry in stateData.items():
			if not isinstance(entry, dict):
				continue
			value = entry.get('value')
			valueType = entry.get('type')
			sender = entry.get('sender', '')
			if value is not None and valueType:
				self.SetValue(key, value, valueType, sender, False)

	###################################################
	# Client Connection
	###################################################

	def HandleClientConnected(self) -> None:
		"""Handle new client connection event."""
		pass

	def BroadcastVals(self) -> None:
		"""Broadcast specified values to connected clients."""
		keys = self.ownerComp.par.Clientconnectedkeys.eval().split(' ')
		for key in keys:
			if self.storeTable.row(key) is not None:
				value = self.storeTable[key, 1]
				valueType = self.storeTable[key, 2].val
				if valueType == self.TYPE_NUMBER:
					self.SetFloat(key, float(value), True)
				elif valueType == self.TYPE_STRING:
					self.SetString(key, value.val, True)
				elif valueType == self.TYPE_BOOLEAN:
					boolValue = value.val.lower() == 'true'
					self.SetBoolean(key, boolValue, True)

	###################################################
	# Defaults
	###################################################

	def SetDefaults(self, force: bool = False) -> None:
		"""
		Set default values from the defaults table.

		Args:
				force: If True, overwrite existing values
		"""
		print('[AppStore] SetDefaults')
		if self.defaultsTable.numRows == 0:
			print('[AppStore] No defaults to set')
			return
		for row in self.defaultsTable.rows():
			key = row[0].val
			value = row[1].val
			valueType = row[2].val
			if key and value and valueType:
				if not self.HasValue(key) or force:
					self.SetValue(key, value, valueType,
						self.getSenderId(), False)

	###################################################
	# File Save/Load
	###################################################

	def SaveFile(self) -> None:
		"""Save the store to a backup file."""
		if absTime.seconds < self.SAVE_FILE_STARTUP_GUARD_SECONDS:
			print('[AppStore] SaveFile skipped - app just started')
			return
		filePath = self.ownerComp.par.Backupfile.eval()
		if filePath:
			# print(f'[AppStore] SaveFile: {filePath}')
			self.storeTable.save(filePath, createFolders=True)

	def LoadFile(self) -> None:
		"""Load the store from a backup file, merging values into existing state."""
		filePath = self.ownerComp.par.Backupfile.eval()
		if not filePath:
			print('[AppStore] LoadFile: no Backupfile path configured, skipping')
			return
		if not os.path.exists(filePath):
			print(f'[AppStore] LoadFile: file not found at {filePath}, skipping')
			return
		print(f'[AppStore] LoadFile: {filePath}')
		self.fileInTable.par.refreshpulse.pulse()
		for row in self.fileInTable.rows():
			if len(row) >= 3:
				key = row[0].val
				value = row[1].val
				valueType = row[2].val
				sender = row[3].val if len(row) > 3 else ''
				self.SetValue(key, value, valueType, sender, False)

	###################################################
	# Debug
	###################################################

	def PrintValues(self) -> None:
		"""Print all values in the store for debugging."""
		print('=== AppStore values: ===')
		for row in self.storeTable.rows():
			print(f"{row[0]}: {row[1]} ({row[2]})")
		print('========================')

	def setColor(self, r: float, g: float, b: float) -> None:
		"""Set the component color indicator."""
		colorIndicator = self.ownerComp.op('constant_active_color')
		colorIndicator.par.colorr = r
		colorIndicator.par.colorg = g
		colorIndicator.par.colorb = b
		self.ownerComp.color = (r, g, b)
