import json
import threading
import time
import uuid
from subprocess import PIPE, STDOUT, Popen
from typing import Any, Callable, Dict, List, Optional, Union


class AppStore:
	"""
	Global state management extension for TouchDesigner.

	Provides a centralized key-value store with type-aware getters/setters,
	WebSocket synchronization, and Python callback listeners.
	"""

	# Value type constants
	TYPE_NUMBER = 'number'
	TYPE_STRING = 'string'
	TYPE_BOOLEAN = 'boolean'

	def __init__(self, ownerComp: baseCOMP) -> None:
		self.ownerComp: baseCOMP = ownerComp
		self.initListeners()
		self.initStore()
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
		"""Check if a key exists in the store."""
		return self.storeTable.row(key) is not None

	def GetFloat(self, key: str, default: float = 0.0) -> float:
		"""Get a numeric value from the store."""
		if self.numericTable[key] is not None:
			return float(self.numericTable[key])
		return default

	def GetString(self, key: str, default: str = '') -> str:
		"""Get a string value from the store."""
		if self.storeTable.row(key) is not None:
			return self.storeTable[key, 1].val
		return default

	def GetBoolean(self, key: str, default: bool = False) -> bool:
		"""Get a boolean value from the store."""
		if self.storeTable.row(key) is not None:
			return self.storeTable[key, 1].val.lower() == 'true'
		return default

	###################################################
	# Setters
	###################################################

	def SetValue(self, key: str, value: Any, valueType: Optional[str] = None, sender: Optional[str] = None, broadcast: bool = False) -> None:
		"""Set a value in the store with optional broadcasting."""
		if broadcast:
			self.broadcastValue(key, value, valueType)
		else:
			eventId = self.newEventId()
			if self.storeTable.row(key) is not None:
				self.storeTable[key, 1] = value
				self.storeTable[key, 2] = valueType
				self.storeTable[key, 3] = sender or ''
				self.storeTable[key, 4] = eventId
			else:
				self.storeTable.appendRow(
					[key, value, valueType, sender, eventId])
			self.NotifyListeners(key, value, valueType)

	def SetFloat(self, key: str, value: float, broadcast: bool = False) -> None:
		"""Set a numeric value in the store."""
		self.SetValue(key, value, self.TYPE_NUMBER,
					self.getSenderId(), broadcast)

	def SetString(self, key: str, value: str, broadcast: bool = False) -> None:
		"""Set a string value in the store."""
		self.SetValue(key, value, self.TYPE_STRING,
					self.getSenderId(), broadcast)

	def SetBoolean(self, key: str, value: bool, broadcast: bool = False) -> None:
		"""Set a boolean value in the store."""
		self.SetValue(key, value, self.TYPE_BOOLEAN,
					self.getSenderId(), broadcast)

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
				print(f"[AppStore] Added listener for *: {listener}")
		elif hasattr(listener, f'On_{key}'):
			keyListeners = self.listenersByKey.setdefault(key, [])
			if listener not in keyListeners:
				print(
					f"[AppStore] Adding listener for key '{key}': {listener}")
				keyListeners.append(listener)
		else:
			print(f"[AppStore] Listener already exists: {listener}")

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
		for listener in self.listeners:
			if hasattr(listener, 'OnAppStoreValueChanged'):
				listener.OnAppStoreValueChanged(key, value, valueType)
			else:
				print(
					f"[AppStore] Listener {listener} does not have OnAppStoreValueChanged method")

		for listener in self.listenersByKey.get(key, []):
			callbackFn = f'On_{key}'
			if hasattr(listener, callbackFn):
				getattr(listener, callbackFn)(key, value, valueType)
			else:
				print(
					f"[AppStore] Listener {listener} does not have {callbackFn} method for key: {key}")

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
		"""Clear all data from the store."""
		self.storeTable.clear()

	def RemoveValue(self, key: str, broadcast: bool = False) -> None:
		"""Remove a value from the store."""
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
		self.setIsConnected(False)
		self.setColor(1, 1, 0)
		self.CheckSocketReconnect()

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
		self.setIsConnected(True)
		self.setColor(0, 1, 0)

	def SocketDisconnected(self, websocketDat: websocketDAT) -> None:
		"""Handle WebSocket disconnection event."""
		self.setIsConnected(False)
		self.setColor(1, 1, 0)

	def MessageReceived(self, dat: tableDAT, rowIndex: int, message: str) -> None:
		"""Handle incoming WebSocket message."""
		data = json.loads(message)

		if data.get('store') == True:
			key = data['key']
			value = data['value']
			valueType = data['type']
			sender = data.get('sender', '')
			self.SetValue(key, value, valueType, sender, False)
		else:
			print('[AppStore] Generic json message received')

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
		if absTime.seconds < 5:
			print('[AppStore] SaveFile skipped - app just started')
			return
		filePath = self.ownerComp.par.Backupfile.eval()
		if filePath:
			# print(f'[AppStore] SaveFile: {filePath}')
			self.storeTable.save(filePath, createFolders=True)

	def LoadFile(self) -> None:
		"""Load the store from a backup file."""
		filePath = self.ownerComp.par.Backupfile.eval()
		if filePath:
			print(f'[AppStore] LoadFile: {filePath}')
			self.fileInTable.par.refreshpulse.pulse()
			self.storeTable.copy(self.fileInTable)

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
