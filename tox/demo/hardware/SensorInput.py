
class SensorInput:
	"""
	SensorInput description
	"""
	def __init__(self, ownerComp: baseCOMP):
		# The component to which this extension is attached
		self.ownerComp: baseCOMP = ownerComp
		self.opSerialDAT: serialDAT = self.ownerComp.op('serial_input')
		self.opFpsHistoryDAT: tableDAT = self.ownerComp.op('table_fps_history')
		self.opInfoHistoryDAT: tableDAT = self.ownerComp.op('table_info_history')
		self.opDataHistoryDAT: tableDAT = self.ownerComp.op('table_data_history')
		self.opTimerTriggerTimeout: timerCHOP = self.ownerComp.op('timer_trigger_timeout')
		self.opTriggerSuccess: triggerCHOP = self.ownerComp.op('trigger_success')
		self.historyLimit = 10
		self.triggerTime = 0

	# Sensor reboot

	def RestartSensor(self):
		self.opSerialDAT.par.active = False
		run(lambda: self.ActivateSensor(), delayFrames=10)
		return

	def ActivateSensor(self):
		self.opSerialDAT.par.active = True
		return

	# Send messages to sensor

	def SendSerialCommand(self, command: str):
		self.opSerialDAT.send(command, terminator='\r\n')
		return

	def SensorSetSettings(self):
		# get settings from pars
		minDist = parent().par.Sensormindistmm.eval()
		maxDist = parent().par.Sensormaxdistmm.eval()
		strength = parent().par.Sensorminstrength.eval()
		print(f'setting sensor minDist: {minDist}, maxDist: {maxDist}, strength: {strength}')

		# send settings via serial
		self.SendSerialCommand('min ' + str(minDist))
		self.SendSerialCommand('max ' + str(maxDist))
		self.SendSerialCommand('strength ' + str(strength))
		self.SendSerialCommand('show')
		return

	def SensorPrintSettings(self):
		self.SendSerialCommand('show')
		return

	# Data update callbacks

	def GetTimestamp(self):
		return absTime.seconds

	def DataUpdated(self, dataStr: str):
		# limit table size: trim oldest entries
		# while self.opDataHistoryDAT.numRows > self.historyLimit:
		# 	self.opDataHistoryDAT.deleteRow(0)
		
		# append new entry with timestamp if we're not in timeout from a trigger
		if self.TimerIsRunning() == False:
			self.opDataHistoryDAT.appendRow([dataStr, self.GetTimestamp()])
		return

	def FPSUpdated(self, fps: float):
		# limit table size: trim oldest entries
		while self.opFpsHistoryDAT.numRows > self.historyLimit:
			self.opFpsHistoryDAT.deleteRow(0)
		# append new entry with timestamp
		self.opFpsHistoryDAT.appendRow([str(fps), self.GetTimestamp()])
		return

	def InfoUpdated(self, infoStr: str):
		# limit table size: trim oldest entries
		while self.opInfoHistoryDAT.numRows > self.historyLimit:
			self.opInfoHistoryDAT.deleteRow(0)

		# append new entry with timestamp
		self.opInfoHistoryDAT.appendRow([infoStr, self.GetTimestamp()])
		return

	# Frame loop checks, largely for trigger sensor and reading clearing

	def TimeWindow(self):
		return parent().par.Triggertimewindow.eval()

	def FrameEndCallback(self):
		# remove data older than time threshold
		timeWindow = self.TimeWindow()
		op.AppStore.SetFloat('sensor_reading_count', self.opDataHistoryDAT.numRows)
		for row in range(self.opDataHistoryDAT.numRows - 1, -1, -1):
			timestamp = float(self.opDataHistoryDAT[row, 1])
			if self.GetTimestamp() - timestamp > timeWindow:
				self.opDataHistoryDAT.deleteRow(row)

		# if we reach a max of readings within the time window, clear out table and trigger sensor success
		if absTime.seconds > self.triggerTime + self.TimeWindow():
			if self.opDataHistoryDAT.numRows >= parent().par.Triggernumreadings:
				self.triggerTime = absTime.seconds
				self.opTimerTriggerTimeout.par.start.pulse()
				run(lambda: self.ClearDataHistory(), delayFrames=3)
				# set app state to triggered
				self.opTriggerSuccess.par.trigger.pulse()
				op.AppStore.SetFloat(op.App.SENSOR_TRIGGERED, 1)
				print(f'{self.opDataHistoryDAT.numRows} readings to TRIGGER')
				# log all 4 sensors data points to appstore as a string
				readings = str(op('math1')[0,0]) + ", " + str(op('math1')[1,0]) + ", " + str(op('math1')[2,0]) + ", " + str(op('math1')[3,0])
				op.AppStore.SetString('sensor_readings', readings)
				return
	
	def ClearDataHistory(self):
		self.opDataHistoryDAT.clear()
		return

	def TimerIsRunning(self):
		fraction = self.opTimerTriggerTimeout['timer_fraction']
		return fraction != 1 and fraction != 0

	def TimeoutTimerComplete(self):
		print('Sensor trigger TIMEOUT completed')
		op.AppStore.SetFloat(op.App.SENSOR_TRIGGERED, 0)
		return

	# Heartbeat callbacks

	def SensorBecameActive(self):
		op.AppStore.SetBoolean(op.App.SENSOR_ACTIVE, True)
		return

	def SensorBecameInactive(self):
		op.AppStore.SetBoolean(op.App.SENSOR_ACTIVE, False)
		return

