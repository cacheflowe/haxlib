

from TDStoreTools import StorageManager
import TDFunctions as TDF
import json

class VideoTriggers:
	"""
	VideoTriggerExt description
	"""
	def __init__(self, ownerComp: baseCOMP):
		# The component to which this extension is attached
		self.ownerComp: baseCOMP = ownerComp
		self.filesDAT: selectDAT = self.ownerComp.op('select_files')
		self.storeKey: str = self.ownerComp.par.Storekey.eval()
		self.files = []
		self.StopAllVideos()
		self.VideosUpdated()

	def StopAllVideos(self):
		videos = self.ownerComp.ops('Video*/moviefilein1')
		for video in videos:
			video.par.play = 0

	def StopAllVideosExcept(self, exceptVideo: moviefileinTOP):
		videos = self.ownerComp.ops('Video*/moviefilein1')
		for video in videos:
			if video != exceptVideo:
				video.par.play = 0
				# print(f'Stopping video: {video.name}')
			# else:
			# 	print(f'Keeping video playing: {video.name}')

	def VideosUpdated(self):
		# create array from first column file strings 
		self.files = []
		for i in range(self.filesDAT.numRows):
			fileName = self.filesDAT[i, 0].val
			fileNoExtension = fileName.split('.')[-2]
			self.files.append(fileNoExtension)
		# print(f"[VideoTriggerExt] Updating video triggers with files: {self.files}")

	def BroadcastVideoTriggers(self):
		# Send to BA app for UI building
		# "_buttons" suffix is used by:
		# - <buttons-for-key> web component component to build the buttons in www
		# - AppStoreArrayButtons in UI .tox to build the buttons in TD
		# when button is clicked, it sends the filename (w/o file extension) via the storeKey
		op.AppStore.SetString(self.storeKey + "_buttons", json.dumps(self.files), broadcast=True)
		# print(f"[VideoTriggerExt] Broadcasted video triggers: {self.files}")
		return

	def GetVideoValues(self):
		return self.files