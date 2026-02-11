# Source: https://github.com/crash7/griffin-powermate

from pywinusb.hid import HidDeviceFilter
from TDStoreTools import StorageManager
import TDFunctions as TDF

class Powermate:
	"""
	Powermate Controller Extension
	"""
	VENDOR = 0x077d
	PRODUCT = 0x0410
	MOVE_LEFT = -1
	MOVE_RIGHT = 1

	def __init__(self, ownerComp):
		# The component to which this extension is attached
		self.ownerComp = ownerComp
		self.device = None
		self.events = {}
		self.eventQueue = []

		# properties
		TDF.createProperty(self, 'Brightness', value=0, dependable=True, readOnly=False)
		TDF.createProperty(self, 'Pulsing', value=False, dependable=True, readOnly=False)
		
		# Try to find and connect to the Powermate
		print("[Powermate] Initializing...")
		self.Connect()

		# config

		# add callbacks
		self.OnEvent('move', self.onMove)
		self.OnEvent('raw', self.onRaw)
		print("[Powermate] Initialized!")

		# op output
		self.opOutputState:constantCHOP = self.ownerComp.op('constant_state')

	# Connection Methods

	def Connect(self):
		self.Close()
		try:
			devices = HidDeviceFilter(vendor_id=self.VENDOR, product_id=self.PRODUCT).get_devices()
			if len(devices) > 0:
				self.device = devices[0]
				self.device.set_raw_data_handler(self._internalListener)
				self.Open()
				# debug(f"Powermate Connected: {self.device}")
				return True
			else:
				debug("Powermate Not Found")
				return False
		except Exception as e:
			debug(f"Powermate Connect Error: {e}")
			return False

	def Open(self):
		if self.device and not self.device.is_opened():
			self.device.open()
			self.SetBrightness(0)
			self.SetLedPulsing(False)


	def Close(self):
		if self.device and self.device.is_opened():
			self.SetLedPulsing(False)
			self.SetBrightness(0)
			self.device.close()
		self.device = None

	# Data listener for Powermate events

	def _internalListener(self, raw_data):
		"""
		[0, button_status, move, 0, bright, pulse_status, pulse_value]
		"""
		# validate data length
		if len(raw_data) < 3: return

		# get rotation direction (-1 = counter-clockwise, 1 = clockwise)
		if raw_data[2] == 1:
			move = 1
		elif raw_data[2] == 255:
			move = -1
		else:
			move = 0
		
		# Callback dispatch
		if 'move' in self.events:
			self.events['move'](move, raw_data[1])
		if 'raw' in self.events:
			self.events['raw'](raw_data)

	def OnEvent(self, event, callback):
		self.events[event] = callback

	# Powermate Commands

	def SetBrightness(self, bright):
		if not self.device: return
		try:
			self.device.send_feature_report([0, 0x41, 0x01, 0x01, 0x00, int(bright) % 255, 0x00, 0x00, 0x00])
			self.Brightness = bright
		except Exception as e:
			debug(f"Error setting brightness: {e}")

	def SetLedPulsing(self, on=True):
		if not self.device: return
		try:
			self.device.send_feature_report([0, 0x41, 0x01, 0x03, 0x00, 0x01 if on else 0x00, 0x00, 0x00, 0x00])
			self.Pulsing = on
		except Exception as e:
			debug(f"Error setting pulsing: {e}")
	
	def SetLedPulsingDefault(self):
		if not self.device: return
		try:
			self.device.send_feature_report([0, 0x41, 0x01, 0x04, 0x00, 0x01, 0x00, 0x00, 0x00])
		except Exception as e:
			debug(f"Error setting pulsing default: {e}")

	# Event Callbacks

	def onMove(self, move, button):
		self.eventQueue.append(('move', move, button))

	def onRaw(self, data):
		self.eventQueue.append(('raw', data))

	# Execute DAT callbacks for threading

	def OnFrameStart(self, frame):
		move = 0
		# button = 0
		if len(self.eventQueue) > 0:
			local_events = self.eventQueue
			self.eventQueue = []
			for event in local_events:
				event_type = event[0]
				if event_type == 'move':
					move, button = event[1], event[2]
					# debug(f"MainThread Process - Move: {move}, Button: {button}")
					self.opOutputState.par.const1value = button
				elif event_type == 'raw':
					data = event[1]
					# debug(f"MainThread Process - Raw: {data}")

		self.opOutputState.par.const0value = move

	def OnFrameEnd(self, frame):
		return

	# Custom behavior 

	def OnActivityChange(self, value):
		brightVal = int(value * 128)
		# print(f"[Powermate] Setting Brightness to {brightVal}")
		self.SetBrightness(brightVal)

	# Cleanup

	def onDestroyTD(self):
		self.Close()
		debug("Powermate Extension Destroyed")