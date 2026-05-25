
class SensorInput:
	"""
	SensorInput description
	"""
	def __init__(self, ownerComp: baseCOMP):
		# The component to which this extension is attached
		self.ownerComp: baseCOMP = ownerComp
		self.opSerialDAT: serialDAT = self.ownerComp.op('serial1')
		self.opConstantReadings: constantCHOP = self.ownerComp.op('constant_sensor_readings')
		self.opFpsHistoryDAT: tableDAT = self.ownerComp.op('table_fps_history')
		self.opInfoHistoryDAT: tableDAT = self.ownerComp.op('table_info_history')
		self.opDistanceHistoryDAT: tableDAT = self.ownerComp.op('table_distance_history')
		self.opVibrationHistoryDAT: tableDAT = self.ownerComp.op('table_vibration_history')
		self.opTimerDistanceTimeout: timerCHOP = self.ownerComp.op('timer_distance_timeout')
		self.opTimerVibrationTimeout: timerCHOP = self.ownerComp.op('timer_vibration_timeout')
		self.opTimerHeartbeatTimeout: timerCHOP = self.ownerComp.op('timer_heartbeat_timeout')
		self.opTriggerSuccess: triggerCHOP = self.ownerComp.op('trigger_success')
		self.historyLimit = 10
		self.distanceTriggerTime = 0
		self.vibrationTriggerTime = 0
		self.lastDistanceTime = 0
		self.lastVibrationTime = 0
		self.lastHeartbeatTime = 0
		self.SensorBecameInactive()


	# Sensor reboot

	def RestartSensor(self):
		self.opSerialDAT.par.active = False
		run(lambda: self.ActivateSensor(), delayFrames=120)
		return

	def ActivateSensor(self):
		try:
			self.opSerialDAT.par.active = True
			self.SensorSetSettings()
		except Exception as e:
			print(f'SensorInput: failed to activate serial - {e}')
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
		piezoMin = parent().par.Sensorpiezomin.eval()

		print(f'sending sensor settings:')
		print(f'- minDist: {minDist}')
		print(f'- maxDist: {maxDist}')
		print(f'- strength: {strength}')
		print(f'- piezoMin: {piezoMin}')

		# send settings via serial
		self.SendSerialCommand('min ' + str(minDist))
		self.SendSerialCommand('max ' + str(maxDist))
		self.SendSerialCommand('strength ' + str(strength))
		self.SendSerialCommand('piezo_min ' + str(piezoMin))
		self.SendSerialCommand('show')
		return

	def SensorPrintSettings(self):
		self.SendSerialCommand('show')
		return

	# Incoming sensor data

	def OnReceive(self, data):
		if data.startswith("d:"):
			dist = float(data[2:])
			self.DistanceUpdated(dist)
		if data.startswith("v:"):
			piezo = float(data[2:])
			self.VibrationUpdated(piezo)
		if data.startswith("h:"):
			fps = float(data[2:])
			self.FPSUpdated(fps)
			self.DoHealthCheckOnValidReading()
		if data.startswith("i:"):
			self.InfoUpdated(data[2:])
		return

	# Data update callbacks

	def GetTimestamp(self):
		return absTime.seconds

	def DistanceUpdated(self, dataStr: float):
		# append new entry with timestamp if we're not in timeout from a trigger
		self.lastDistanceTime = self.GetTimestamp()
		self.opConstantReadings.par.const0value = float(dataStr)
		if self.DistanceTimerIsRunning() == False:
			self.opDistanceHistoryDAT.appendRow([dataStr, self.GetTimestamp()])
		return

	def VibrationUpdated(self, piezo: float):
		# append new entry with timestamp if we're not in timeout from a trigger
		self.lastVibrationTime = self.GetTimestamp()
		self.opConstantReadings.par.const1value = float(piezo)
		if self.VibrationTimerIsRunning() == False:
			self.opVibrationHistoryDAT.appendRow([piezo, self.GetTimestamp()])
		return

	def FPSUpdated(self, fps: float):
		self.opConstantReadings.par.const2value = float(fps)
		# set timeout for disconnected indicator
		self.opTimerHeartbeatTimeout.par.start.pulse()
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

	def DistanceTimeWindow(self):
		return parent().par.Triggertimewindow.eval()
	
	def DistanceNumReadings(self):
		return parent().par.Triggernumreadings.eval()

	def VibrationTimeWindow(self):
		return parent().par.Triggertimewindow.eval()

	def VibrationNumReadings(self):
		return parent().par.Piezonumreadings.eval()

	def PruneHistory(self, historyDAT, timeWindow):
		for row in range(historyDAT.numRows - 1, -1, -1):
			timestamp = float(historyDAT[row, 1])
			if self.GetTimestamp() - timestamp > timeWindow:
				historyDAT.deleteRow(row)

	def CheckSensorTrigger(self, historyDAT, timeWindow, numReadings, lastTriggerTime, timerOp, clearMethod, appStoreKey):
		if absTime.seconds > lastTriggerTime + timeWindow: # ignore readings while timer is running
			if historyDAT.numRows >= numReadings:
				timerOp.par.start.pulse()
				run(lambda: clearMethod(), delayFrames=3)
				op.AppStore.SetFloat(appStoreKey, 1, broadcast=True)
				return absTime.seconds
		return lastTriggerTime

	def FrameEndCallback(self):
		self.CheckResetChopData()

		# process distance sensor
		distWindow = self.DistanceTimeWindow()
		distReadings = self.DistanceNumReadings()
		self.PruneHistory(self.opDistanceHistoryDAT, distWindow)
		self.distanceTriggerTime = self.CheckSensorTrigger(
			self.opDistanceHistoryDAT, distWindow, distReadings, self.distanceTriggerTime,
			self.opTimerDistanceTimeout, self.ClearDistanceHistory, op.App.SENSOR_HOOP)

		# process vibration sensor
		vibWindow = self.VibrationTimeWindow()
		vibNumReadings = self.VibrationNumReadings()
		self.PruneHistory(self.opVibrationHistoryDAT, vibWindow)
		self.vibrationTriggerTime = self.CheckSensorTrigger(
			self.opVibrationHistoryDAT, vibWindow, vibNumReadings, self.vibrationTriggerTime,
			self.opTimerVibrationTimeout, self.ClearVibrationHistory, op.App.SENSOR_BACKBOARD)
	
	def CheckResetChopData(self):
		if self.GetTimestamp() - self.lastDistanceTime > self.DistanceTimeWindow():
			self.opConstantReadings.par.const0value = 0
		if self.GetTimestamp() - self.lastVibrationTime > self.VibrationTimeWindow():
			self.opConstantReadings.par.const1value = 0


	def ClearDistanceHistory(self):
		self.opDistanceHistoryDAT.clear()
		return

	def ClearVibrationHistory(self):
		self.opVibrationHistoryDAT.clear()
		return

	def DistanceTimerIsRunning(self):
		fraction = self.opTimerDistanceTimeout['timer_fraction']
		return fraction != 1 and fraction != 0

	def VibrationTimerIsRunning(self):
		fraction = self.opTimerVibrationTimeout['timer_fraction']
		return fraction != 1 and fraction != 0

	def TimeoutDistanceComplete(self):
		op.AppStore.SetFloat(op.App.SENSOR_HOOP, 0, broadcast=True)
		return

	def TimeoutVibrationComplete(self):
		op.AppStore.SetFloat(op.App.SENSOR_BACKBOARD, 0, broadcast=True)
		return

	# Heartbeat callbacks

	def SensorBecameActive(self):
		op.AppStore.SetBoolean(op.App.SENSOR_HEALTH, True, broadcast=True)
		return

	def SensorBecameInactive(self):
		op.AppStore.SetBoolean(op.App.SENSOR_HEALTH, False, broadcast=True)
		return

	def DoHealthCheckOnValidReading(self):
		if op.AppStore.GetBoolean(op.App.SENSOR_HEALTH, False) == False:
			op.AppStore.SetBoolean(op.App.SENSOR_HEALTH, True, broadcast=True)